from pycket        import values
from pycket        import vector
from pycket        import proc
from pycket.prims  import prim_env
from pycket.error  import SchemeException
from rpython.rlib  import jit, debug


def inline_small_list(cls, sizemax=5, sizemin=0, immutable=False, attrname="list"):
    """ This function is helpful if you have a class with a field storing a
list and the list is often very small. Calling this function will inline
the list into instances for the small sizes. This works by adding the
following methods to the class:

_get_list(self, i): return ith element of the list

_set_list(self, i, val): set ith element of the list

_get_full_list(self): returns a copy of the full list

@staticmethod
make(listcontent, *args): makes a new instance with the list's content set to listcontent
        """
    from rpython.rlib.unroll import unrolling_iterable
    classes = []
    def make_methods(size):
        attrs = ["_%s_%s" % (attrname, i) for i in range(size)]
        unrolling_enumerate_attrs = unrolling_iterable(enumerate(attrs))
        def _get_size_list(self):
            return size
        def _get_list(self, i):
            for j, attr in unrolling_enumerate_attrs:
                if j == i:
                    return getattr(self, attr)
            raise IndexError
        def _get_full_list(self):
            res = [None] * size
            for i, attr in unrolling_enumerate_attrs:
                res[i] = getattr(self, attr)
            return res
        def _set_list(self, i, val):
            for j, attr in unrolling_enumerate_attrs:
                if j == i:
                    return setattr(self, attr, val)
            raise IndexError
        def _init(self, elems, *args):
            assert len(elems) == size
            for i, attr in unrolling_enumerate_attrs:
                setattr(self, attr, elems[i])
            cls.__init__(self, *args)
        meths = {"_get_list": _get_list, "_get_size_list": _get_size_list, "_get_full_list": _get_full_list, "_set_list": _set_list, "__init__" : _init}
        if immutable:
            meths["#_immutable_fields_"] = attrs
        return meths
    classes = [type(cls)("%sSize%s" % (cls.__name__, size), (cls, ), make_methods(size)) for size in range(sizemin, sizemax)]
    def _get_arbitrary(self, i):
        return getattr(self, attrname)[i]
    def _get_size_list_arbitrary(self):
        return len(getattr(self, attrname))
    def _get_list_arbitrary(self):
        return getattr(self, attrname)
    def _set_arbitrary(self, i, val):
        getattr(self, attrname)[i] = val
    def _init(self, elems, *args):
        debug.make_sure_not_resized(elems)
        setattr(self, attrname, elems)
        cls.__init__(self, *args)
    meths = {"_get_list": _get_arbitrary, "_get_size_list": _get_size_list_arbitrary, "_get_full_list": _get_list_arbitrary, "_set_list": _set_arbitrary, "__init__": _init}
    if immutable:
        meths["#_immutable_fields_"] = ["%s[*]" % (attrname, )]
    cls_arbitrary = type(cls)("%sArbitrary" % cls.__name__, (cls, ), meths)

    @staticmethod
    def make(elems, *args):
        if sizemin <= len(elems) < sizemax:
            cls = classes[len(elems) - sizemin]
        else:
            cls = cls_arbitrary
        return cls(elems, *args)
    cls.make = make

class Env(object):
    #_immutable_fields_ = ["toplevel_env"]
    pass

class Version(object):
    pass

class ToplevelEnv(object):
    #_immutable_fields_ = ["version"]
    def __init__(self):
        self.bindings = {}
        self.version = Version()
    def lookup(self, sym):
        jit.promote(self)
        w_res = self._lookup(sym, jit.promote(self.version))
        if isinstance(w_res, values.W_Cell):
            w_res = w_res.value
        return w_res

    @jit.elidable
    def _lookup(self, sym, version):
        try:
            return self.bindings[sym]
        except KeyError:
            raise SchemeException("toplevel variable %s not found" % sym.value)

    def set(self, sym, w_val):
        if sym in self.bindings:
            self.bindings[sym].value = w_val
        else:
            self.bindings[sym] = values.W_Cell(w_val)
            self.version = Version()

class EmptyEnv(Env):
    def __init__ (self, toplevel):
        self.toplevel_env = toplevel
    def lookup(self, sym):
        raise SchemeException("variable %s is unbound"%sym.value)

class ConsEnv(Env):
    #_immutable_fields_ = ["args", "prev"]
    @jit.unroll_safe
    def __init__ (self, args, prev, toplevel):
        self.toplevel_env = toplevel
        self.args = args
        self.prev = prev
    @jit.unroll_safe
    def lookup(self, sym):
        jit.promote(self.args)
        for i, s in enumerate(self.args.elems):
            if s is sym:
                v = self._get_list(i)
                assert v is not None
                return v
        return self.prev.lookup(sym)
    def set(self, sym, val):
        jit.promote(self.args)
        for i, s in enumerate(self.args.elems):
            if s is sym:
                self._set_list(i, val)
                return
        return self.prev.set(sym, val)
inline_small_list(ConsEnv, immutable=True, attrname="vals")

class Cont(object):
    def tostring(self):
        if self.prev:
            return "%s(%s)"%(self.__class__.__name__,self.prev.tostring())
        else:
            return "%s()"%(self.__class__.__name__)

class IfCont(Cont):
    def __init__(self, ast, env, prev):
        self.ast = ast
        self.env = env
        self.prev = prev
    def plug_reduce(self, w_val):
        # remove the frame created by the let introduced by let_convert
        # it's no longer needed nor accessible
        env = self.env
        assert env._get_size_list() == 1
        assert isinstance(env, ConsEnv)
        env = env.prev
        ast = jit.promote(self.ast)
        if w_val is values.w_false:
            return ast.els, env, self.prev
        else:
            return ast.thn, env, self.prev

class LetrecCont(Cont):
    def __init__(self, ast, i, env, prev):
        self.ast = ast
        self.i = i
        self.env  = env
        self.prev = prev
    def plug_reduce(self, w_val):
        #import pdb; pdb.set_trace()
        v = self.env.lookup(self.ast.args.elems[self.i])
        assert isinstance(v, values.W_Cell)
        v.value = w_val
        if self.i >= (len(self.ast.rhss) - 1):
            return self.ast.make_begin_cont(self.env, self.prev)
        else:
            return (self.ast.rhss[self.i + 1], self.env,
                    LetrecCont(self.ast, self.i + 1,
                               self.env, self.prev))

class LetCont(Cont):
    def __init__(self, ast, env, prev):
        self.ast = ast
        self.env  = env
        self.prev = prev
    def plug_reduce(self, w_val):
        ast = jit.promote(self.ast)
        if self._get_size_list() == (len(ast.rhss) - 1):
            vals_w = self._get_full_list() + [w_val]
            env = ConsEnv.make(vals_w, ast.args, self.env, self.env.toplevel_env)
            return ast.make_begin_cont(env, self.prev)
        else:
            return (ast.rhss[self._get_size_list() + 1], self.env,
                    LetCont.make(self._get_full_list() + [w_val], ast,
                            self.env, self.prev))
inline_small_list(LetCont, attrname="vals_w")

class CellCont(Cont):
    def __init__(self, env, prev):
        self.env = env
        self.prev = prev
    def plug_reduce(self, w_val):
        return Value(values.W_Cell(w_val)), self.env, self.prev

class Call(Cont):
    # prev is the parent continuation
    def __init__ (self, ast, env, prev):
        self.ast = ast
        self.env = env
        self.prev = prev
    def plug_reduce(self, w_val):
        ast = jit.promote(self.ast)
        if self._get_size_list() == len(ast.rands):
            vals_w = self._get_full_list() + [w_val]
            #print vals_w[0]
            env = self.env
            assert isinstance(env, ConsEnv)
            assert len(vals_w) == len(ast.rands) + 1
            # remove the frame created by the let introduced by let_convert
            # it's no longer needed nor accessible
            env = env.prev
            return vals_w[0].call(vals_w[1:], env, self.prev)
        else:
            return ast.rands[self._get_size_list()], self.env, Call.make(self._get_full_list() + [w_val], ast,
                                                          self.env, self.prev)
inline_small_list(Call, attrname="vals_w")

class SetBangCont(Cont):
    def __init__(self, var, env, prev):
        self.var = var
        self.env = env
        self.prev = prev
    def plug_reduce(self, w_val):
        self.var._set(w_val, self.env)
        return Value(values.w_void), self.env, self.prev

class BeginCont(Cont):
    def __init__(self, ast, i, env, prev):
        self.ast = ast
        self.i = i
        self.env = env
        self.prev = prev
    def plug_reduce(self, w_val):
        return self.ast.make_begin_cont(self.env, self.prev, self.i)

class Done(Exception):
    def __init__(self, w_val):
        self.w_val = w_val

class AST(object):
    def let_convert(self):
        return self
    def free_vars(self):
        return {}


class Value(AST):
    def __init__ (self, w_val):
        self.w_val = w_val
    def interpret(self, env, frame):
        if frame is None: raise Done(self.w_val)
        return frame.plug_reduce(self.w_val)
    def let_convert(self):
        assert 0
    def assign_convert(self, vars):
        return self
    def mutated_vars(self):
        return {}
    def tostring(self):
        return "V(%s)"%self.w_val.tostring()

class Cell(AST):
    def __init__(self, expr):
        self.expr = expr
    def interpret(self, env, frame):
        return self.expr, env, CellCont(env, frame)
    def let_convert(self):
        assert 0
    def assign_convert(self, vars):
        return Cell(self.expr.assign_convert(vars))
    def mutated_vars(self):
        return self.expr.mutated_vars()
    def free_vars(self):
        return self.expr.free_vars()
    def tostring(self):
        return "Cell(%s)"%self.expr

class Quote(AST):
    #_immutable_fields_ = ["w_val"]
    def __init__ (self, w_val):
        self.w_val = w_val
    def interpret(self, env, frame):
        return Value(self.w_val), env, frame
    def assign_convert(self, vars):
        return self
    def mutated_vars(self):
        return {}
    def tostring(self):
        return "'%s"%self.w_val.tostring()

class App(AST):
    #_immutable_fields_ = ["rator", "rands[*]"]
    def __init__ (self, rator, rands):
        self.rator = rator
        self.rands = rands
    def let_convert(self):
        # Generate fresh symbols and variables for the operator and operands
        fresh_rator = LexicalVar.gensym("AppRator_")
        fresh_rator_var = LexicalVar(fresh_rator)
        fresh_rands = [LexicalVar.gensym("AppRand%s_"%i) for i, _ in enumerate(self.rands)]
        fresh_rands_vars = [LexicalVar(fresh) for fresh in fresh_rands]
        # Create a Let binding the fresh symbols to the original values
        fresh_vars = [fresh_rator] + fresh_rands
        fresh_rhss = [self.rator] + self.rands
        # The body is an App operating on the freshly bound symbols
        fresh_body = [App(fresh_rator_var, fresh_rands_vars)]
        return Let(fresh_vars, fresh_rhss, fresh_body)
    def assign_convert(self, vars):
        return App(self.rator.assign_convert(vars),
                   [e.assign_convert(vars) for e in self.rands])
    def mutated_vars(self):
        x = self.rator.mutated_vars()
        for r in self.rands:
            x.update(r.mutated_vars())
        return x
    def free_vars(self):
        x = self.rator.free_vars()
        for r in self.rands:
            x.update(r.free_vars())
        return x
    def interpret(self, env, frame):
        return self.rator, env, Call.make([], self, env, frame)
    def tostring(self):
        return "(%s %s)"%(self.rator.tostring(), " ".join([r.tostring() for r in self.rands]))

class SequencedBodyAST(AST):
    #_immutable_fields_ = ["body[*]"]
    def __init__(self, body):
        assert isinstance(body, list)
        assert len(body) > 0
        self.body = body

    def make_begin_cont(self, env, prev, i=0):
        if i == len(self.body) - 1:
            return self.body[i], env, prev
        else:
            return self.body[i], env, BeginCont(self, i + 1, env, prev)


class Begin(SequencedBodyAST):
    @staticmethod
    def make(body):
        if len(body) == 1:
            return body[0]
        else:
            return Begin(body)
    def assign_convert(self, vars):
        return Begin.make([e.assign_convert(vars) for e in self.body])
    def mutated_vars(self):
        x = {}
        for r in self.body:
            x.update(r.mutated_vars())
        return x
    def free_vars(self):
        x = {}
        for r in self.body:
            x.update(r.free_vars())
        return x
    def interpret(self, env, frame):
        return self.make_begin_cont(env, frame)
    def tostring(self):
        return "(begin %s)" % (" ".join([e.tostring() for e in self.body]))

class Var(AST):
    #_immutable_fields_ = ["sym"]
    def __init__ (self, sym):
        self.sym = sym
    def interpret(self, env, frame):
        return Value(self._lookup(env)), env, frame
    def mutated_vars(self):
        return {}
    def free_vars(self):
        return {self.sym: None}
    def tostring(self):
        return "%s"%self.sym.value

class CellRef(Var):
    def assign_convert(self, vars):
        return self
    def tostring(self):
        return "CellRef(%s)"%self.sym.value
    def _set(self, w_val, env):
        v = env.lookup(self.sym)
        assert isinstance(v, values.W_Cell)
        v.value = w_val
    def _lookup(self, env):
        #import pdb; pdb.set_trace()
        v = env.lookup(self.sym)
        assert isinstance(v, values.W_Cell)
        return v.value

# Using this in rpython to have a mutable global variable
class Counter(object):
    value = 0


class LexicalVar(Var):
    _counter = Counter()
    @staticmethod
    def gensym(hint=""):
        LexicalVar._counter.value += 1
        # not using `make` so that it's really gensym
        return values.W_Symbol(hint + "fresh_" + str(LexicalVar._counter.value))
    def _lookup(self, env):
        return env.lookup(self.sym)
    def _set(self, w_val, env): 
        assert 0
    def assign_convert(self, vars):
        if self.sym in vars:
            return CellRef(self.sym)
        else:
            return self

class ModuleVar(Var):
    def _lookup(self, env):
        return self._prim_lookup()
    def free_vars(self): return {}
    @jit.elidable
    def _prim_lookup(self):
        return prim_env[self.sym]
    def assign_convert(self, vars):
        return self
    def _set(self, w_val, env): assert 0

class ToplevelVar(Var):
    def _lookup(self, env):
        return env.toplevel_env.lookup(self.sym)
    def free_vars(self): return {}
    def assign_convert(self, vars):
        return self
    def _set(self, w_val, env):
        env.toplevel_env.set(self.sym, w_val)

class SymList(object):
    #_immutable_fields_ = ["elems[*]"]
    def __init__(self, elems):
        assert isinstance(elems, list)
        self.elems = elems

class SetBang(AST):
    #_immutable_fields_ = ["sym", "rhs"]
    def __init__(self, var, rhs):
        self.var = var
        self.rhs = rhs
    def interpret(self, env, frame):
        return self.rhs, env, SetBangCont(self.var, env, frame)
    def assign_convert(self, vars):
        return SetBang(self.var, self.rhs.assign_convert(vars))
    def mutated_vars(self):
        x = self.rhs.mutated_vars()
        x[self.var.sym] = None
        return x
    def free_vars(self):
        x = self.rhs.free_vars()
        x[self.var.sym] = None
        return x
    def tostring(self):
        return "(set! %s %s)"%(self.var.sym.value, self.rhs)

class If(AST):
    #_immutable_fields_ = ["tst", "thn", "els"]
    def __init__ (self, tst, thn, els):
        self.tst = tst
        self.thn = thn
        self.els = els
    def let_convert(self):
        fresh = LexicalVar.gensym("if_")
        return Let([fresh], [self.tst], [If(LexicalVar(fresh), self.thn, self.els)])
    def interpret(self, env, frame):
        return self.tst, env, IfCont(self, env, frame)
    def assign_convert(self, vars):
        return If(self.tst.assign_convert(vars),
                  self.thn.assign_convert(vars),
                  self.els.assign_convert(vars))
    def mutated_vars(self):
        x = {}
        for b in [self.tst, self.els, self.thn]:
            x.update(b.mutated_vars())
        return x
    def free_vars(self):
        x = {}
        for b in [self.tst, self.els, self.thn]:
            x.update(b.free_vars())
        return x
    def tostring(self):
        return "(if %s %s %s)"%(self.tst.tostring(), self.thn.tostring(), self.els.tostring())

class RecLambda(AST):
    #_immutable_fields_ = ["name", "lam"]
    def __init__(self, name, lam):
        self.name= name
        self.lam = lam
    def assign_convert(self, vars):
        v = vars.copy()
        if self.name in v:
            del v[self.name]
        return RecLambda(self.name, self.lam.assign_convert(v))
    def mutated_vars(self):
        v = self.lam.mutated_vars()
        if self.name in v:
            del v[self.name]
        return v
    def free_vars(self):
        v = self.lam.free_vars()
        if self.name in v:
            del v[self.name]
        return v
    def interpret(self, env, frame):
        e = ConsEnv.make([values.w_void], SymList([self.name]), env, env.toplevel_env)
        Vcl, e, f = self.lam.interpret(e, frame)
        cl = Vcl.w_val
        assert isinstance(cl, proc.W_Closure)
        cl.env.set(self.name, cl)
        return Vcl, env, frame
    def tostring(self):
        if self.lam.rest and (not self.lam.formals):
            return "(rec %s %s %s)"%(self.name, self.lam.rest, self.lam.body)
        if self.lam.rest:
            return "(rec %s (%s . %s) %s)"%(self.name, self.lam.formals, self.lam.rest, self.lam.body)
        else:
            return "(rec %s (%s) %s)"%(self.name, self.lam.formals, self.lam.body)


class Lambda(SequencedBodyAST):
    #_immutable_fields_ = ["formals[*]", "rest", "args", "frees[*]"]
    def do_anorm(self):
        return Lambda(self.formals, self.rest, [anorm_and_bind(Begin.make(self.body))])
    def __init__ (self, formals, rest, body):
        SequencedBodyAST.__init__(self, body)
        self.formals = formals
        self.rest = rest
        self.args = SymList(formals + ([rest] if rest else []))
        self.frees = SymList(self.free_vars().keys())
    def interpret(self, env, frame):
        return Value(proc.W_Closure(self, env)), env, frame
    def assign_convert(self, vars):
        local_muts = {}
        for b in self.body:
            local_muts.update(b.mutated_vars())
        new_lets = []
        new_vars = vars.copy()
        for i in self.args.elems:
            if i in new_vars:
                del new_vars[i]
            if i in local_muts:
                new_lets.append(i)
        cells = [Cell(LexicalVar(v)) for v in new_lets]
        new_vars.update(local_muts)
        new_body = [make_let(new_lets, cells, [b.assign_convert(new_vars) for b in self.body])]
        return Lambda(self.formals, self.rest, new_body)
    def mutated_vars(self):
        x = {}
        for b in self.body:
            x.update(b.mutated_vars())
        for v in self.formals:
            if v in x:
                del x[v]
        if self.rest and self.rest in x:
            del x[self.rest]
        return x
    def free_vars(self):
        x = {}
        for b in self.body:
            x.update(b.free_vars())
        for v in self.formals:
            if v in x:
                del x[v]
        if self.rest and self.rest in x:
            del x[self.rest]
        return x
    def tostring(self):
        if self.rest and (not self.formals):
            return "(lambda %s %s)"%(self.rest, [b.tostring() for b in self.body])
        if self.rest:
            return "(lambda (%s . %s) %s)"%(self.formals, self.rest, [b.tostring() for b in self.body])
        else:
            return "(lambda (%s) %s)"%(self.formals, [b.tostring() for b in self.body])


class Letrec(SequencedBodyAST):
    #_immutable_fields_ = ["vars[*]", "rhss[*]"]
    def __init__(self, vars, rhss, body):
        SequencedBodyAST.__init__(self, body)
        self.vars = vars
        self.rhss = rhss
        self.args = SymList(vars)
    def interpret(self, env, frame):
        env_new = ConsEnv.make([values.W_Cell(None) for var in self.vars], self.args, env, env.toplevel_env)
        return self.rhss[0], env_new, LetrecCont(self, 0, env_new, frame)
    def mutated_vars(self):
        x = {}
        for b in self.body + self.rhss:
            x.update(b.mutated_vars())
        for v in self.vars:
            x[v] = None
        return x
    def free_vars(self):
        x = {}
        for b in self.body + self.rhss:
            x.update(b.free_vars())
        for v in self.vars:
            if v in x:
                del x[v]
        return x
    def assign_convert(self, vars):
        local_muts = {}
        for b in self.body + self.rhss:
            local_muts.update(b.mutated_vars())
        for v in self.vars:
            local_muts[v] = None
        new_vars = vars.copy()
        new_vars.update(local_muts)
        new_rhss = [rhs.assign_convert(new_vars) for rhs in self.rhss]
        new_body = [b.assign_convert(new_vars) for b in self.body]
        return Letrec(self.vars, new_rhss, new_body)
    def tostring(self):
        return "(letrec (%s) %s)"%([(v.tostring(),self.rhss[i].tostring()) for i, v in enumerate(self.vars)], 
                                   [b.tostring() for b in self.body])

def make_let_star(bindings, body):
    if not bindings:
        return Begin.make(body)
    var, rhs = bindings[0]
    if len(body) == 1 and isinstance(body[0], LexicalVar) and (body[0].sym is var):
        return rhs
    else:
        return Let([var], [rhs], [make_let_star(bindings[1:], body)])

def make_let(vars, rhss, body):
    if not vars:
        return Begin.make(body)
    else:
        return Let(vars, rhss, body)

def make_letrec(vars, rhss, body):
    if (1 == len(vars)):
        if (1 == len(body)):
            if isinstance(rhss[0], Lambda):
                if isinstance(body[0], LexicalVar) and vars[0] is body[0].sym:
                    return RecLambda(vars[0], rhss[0])
    return Letrec(vars, rhss, body)

class Let(SequencedBodyAST):
    # Not sure why, but rpython keeps telling me that vars is resized...
    #_immutable_fields_ = ["vars[*]", "rhss[*]", "args"]
    def __init__(self, vars, rhss, body):
        self.vars = vars
        SequencedBodyAST.__init__(self, body)
        assert isinstance(vars, list)
        assert len(vars) > 0 # otherwise just use a begin
        self.rhss = rhss
        self.args = SymList(vars)
    def interpret(self, env, frame):
        return self.rhss[0], env, LetCont.make([], self, env, frame)
    def mutated_vars(self):
        x = {}
        for b in self.body:
            x.update(b.mutated_vars())
        x2 = {}
        for v in x:
            if v not in self.vars:
                x2[v] = x[v]
        for b in self.rhss:
            x2.update(b.mutated_vars())
        return x2
    def free_vars(self):
        x = {}
        for b in self.body:
            x.update(b.free_vars())
        for v in self.vars:
            if v in x:
                del x[v]
        for b in self.rhss:
            x.update(b.free_vars())
        return x
    def assign_convert(self, vars):
        local_muts = {}
        for b in self.body:
            local_muts.update(b.mutated_vars())
        new_rhss = [Cell(rhs.assign_convert(vars))
                    if self.vars[i] in local_muts
                    else rhs.assign_convert(vars)
                    for i, rhs in enumerate(self.rhss)]
        new_vars = vars.copy()
        new_vars.update(local_muts)
        new_body = [b.assign_convert(new_vars) for b in self.body]
        return Let(self.vars, new_rhss, new_body)
    def tostring(self):
        return "(let (%s) %s)"%(" ".join(["[%s %s]" % (v.tostring(),self.rhss[i].tostring()) for i, v in enumerate(self.vars)]), 
                                " ".join([b.tostring() for b in self.body]))


class Define(AST):
    def __init__(self, name, rhs):
        self.name = name
        self.rhs = rhs
    def assign_convert(self, vars):
        return Define(self.name, self.rhs.assign_convert(vars))
    def mutated_vars(self): assert 0
    def free_vars(self): assert 0
    def tostring(self):
        return "(define %s %s)"%(self.name, self.rhs.tostring())

def get_printable_location(green_ast):
    if green_ast is None:
        return 'Green_Ast is None'
    return green_ast.tostring()
driver = jit.JitDriver(reds=["ast", "env", "frame"],
                       greens=["green_ast"],
                       get_printable_location=get_printable_location)

def interpret_one(ast, env=None):
    frame = None
    if not env:
        env = EmptyEnv(ToplevelEnv())
    green_ast = None
    try:
        while True:
            driver.jit_merge_point(ast=ast, env=env, frame=frame, green_ast=green_ast)
            if not isinstance(ast, Value):
                jit.promote(ast)
                green_ast = ast
            
            #print ast.tostring()
            # if frame:
            #     if len(frame.tostring()) > 250:
            #         import pdb; pdb.set_trace()
            #     #print frame.tostring()
            ast, env, frame = ast.interpret(env, frame)
            if isinstance(ast, App):
                driver.can_enter_jit(ast=ast, env=env, frame=frame, green_ast=green_ast)
    except Done, e:
        return e.w_val

def interpret_toplevel(a, env):
    if isinstance(a, Begin):
        x = None
        for a2 in a.body:
            x = interpret_toplevel(a2, env)
        return x
    elif isinstance(a, Define):
        env.toplevel_env.set(a.name, interpret_one(a.rhs, env))
        return values.w_void
    else:
        return interpret_one(a, env)
    

def interpret(asts):
    env = EmptyEnv(ToplevelEnv())
    x = None
    for a in asts:
        x = interpret_toplevel(a, env)
    return x


