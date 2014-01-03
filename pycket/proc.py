
from pycket.values import W_Object
from pycket.cons import to_list
from rpython.rlib  import jit
from pycket.error import SchemeException

class W_Procedure(W_Object):
    errorname = "procedure"
    def __init__(self):
        raise NotImplementedError("abstract base class")

class W_SimplePrim(W_Procedure):
    _immutable_fields_ = ["name", "code"]
    def __init__ (self, name, code):
        self.name = name
        self.code = code

    def call(self, args, env, frame):
        from pycket.interpreter import Value
        jit.promote(self)
        #print self.name
        return Value(self.code(args)), env, frame
    
    def tostring(self):
        return "SimplePrim<%s>" % self.name

class W_Prim(W_Procedure):
    _immutable_fields_ = ["name", "code"]
    def __init__ (self, name, code):
        self.name = name
        self.code = code

    def call(self, args, env, frame):
        jit.promote(self)
        return self.code(args, env, frame)
    
    def tostring(self):
        return "Prim<%s>" % self.name

class W_Continuation(W_Procedure):
    _immutable_fields_ = ["frame"]
    def __init__ (self, frame):
        self.frame = frame
    def call(self, args, env, frame):
        from pycket.interpreter import Value
        a, = args # FIXME: multiple values
        return Value(a), env, self.frame

class W_Closure(W_Procedure):
    _immutable_fields_ = ["lam", "env"]
    @jit.unroll_safe
    def __init__ (self, lam, env):
        from pycket.interpreter import ConsEnv, EmptyEnv
        self.lam = lam
        vals = [env.lookup(i) for i in lam.frees.elems]
        self.env = ConsEnv.make(vals, lam.frees, EmptyEnv(env.toplevel_env), env.toplevel_env)
    def call(self, args, env, frame):
        from pycket.interpreter import ConsEnv
        lam = jit.promote(self.lam)
        fmls_len = len(lam.formals)
        args_len = len(args)
        if fmls_len != args_len and not lam.rest:
            raise SchemeException("wrong number of arguments to %s, expected %s but got %s"%(self.tostring(), fmls_len,args_len))
        if fmls_len > args_len:
            raise SchemeException("wrong number of arguments to %s, expected at least %s but got %s"%(self.tostring(), fmls_len,args_len))
        if lam.rest:
            actuals = args[0:fmls_len] + [to_list(args[fmls_len:])]
        else:
            actuals = args
        # specialize on the fact that often we end up executing in the same
        # environment
        if isinstance(env, ConsEnv) and env.prev is self.env:
            prev = env.prev
        else:
            prev = self.env
        return lam.make_begin_cont(
                          ConsEnv.make(actuals, lam.args, prev, self.env.toplevel_env),
                          frame)
