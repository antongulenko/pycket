import operator
import os
from pycket import values
from pycket import proc
from pycket import cons
from pycket import vector as vec
from pycket import cons
from pycket import arithmetic # imported for side effect
from pycket.error import SchemeException
from rpython.rlib  import jit, unroll

prim_env = {}

def expose(name, argstypes=None, simple=True):
    def wrapper(func):
        if argstypes is not None:
            unroll_argtypes = unroll.unrolling_iterable(enumerate(argstypes))
            arity = len(argstypes)
            errormsg_arity = "expected %s arguments to %s, got %%s" % (arity, name)
            for typ in argstypes:
                assert typ.__dict__["errorname"]
            def wrap_func(args, *rest):
                if len(args) != arity:
                    raise SchemeException(errormsg_arity % len(args))
                typed_args = ()
                for i, typ in unroll_argtypes:
                    arg = args[i]
                    if typ is not values.W_Object and not isinstance(arg, typ):
                        raise SchemeException("expected %s as argument to %s, got %s" % (typ.errorname, name, args[i].tostring()))
                    typed_args += (arg, )
                typed_args += rest
                result = func(*typed_args)
                if result is None:
                    return values.w_void
                return result
        else:
            def wrap_func(*args):
                result = func(*args)
                if result is None:
                    return values.w_void
                return result
        wrap_func.func_name = "wrap_%s" % (func.func_name, )
        if simple:
            cls = proc.W_SimplePrim
        else:
            cls = proc.W_Prim
        prim_env[values.W_Symbol.make(name)] = cls(name, wrap_func)
        return wrap_func
    return wrapper

def val(name, v):
    prim_env[values.W_Symbol.make(name)] = v

def make_cmp(name, op, con):
    @expose(name, [values.W_Number, values.W_Number], simple=True)
    def do(a, b):
        if isinstance(a, values.W_Fixnum) and isinstance(b, values.W_Fixnum):
            return con(getattr(operator, op)(a.value, b.value))
        if isinstance(a, values.W_Bignum) and isinstance(b, values.W_Bignum):
            return con(getattr(a.value, op)(b.value))
        if isinstance(a, values.W_Flonum) and isinstance(b, values.W_Flonum):
            return con(getattr(operator, op)(a.value, b.value))
        raise SchemeException("unsupported operation %s on %s %s" % (name, a.tostring(), b.tostring()))

for args in [
        ("=", "eq", values.W_Bool.make),
        ("<", "lt", values.W_Bool.make),
        (">", "gt", values.W_Bool.make),
        ("<=", "le", values.W_Bool.make),
        (">=", "ge", values.W_Bool.make),
        ]:
    make_cmp(*args)


def make_pred(name, cls):
    @expose(name, [values.W_Object], simple=True)
    def do(a):
        return values.W_Bool.make(isinstance(a, cls))

def make_pred_eq(name, val):
    typ = type(val)
    @expose(name, [values.W_Object], simple=True)
    def do(a):
        return values.W_Bool.make(isinstance(a, typ) and a is val)


for args in [
        ("pair?", cons.W_Cons),
        ("number?", values.W_Number),
        ("vector?", vec.W_Vector),
        ("string?", values.W_String),
        ("symbol?", values.W_Symbol),
        ("boolean?", values.W_Bool),
        ("procedure?", proc.W_Procedure),
        ]:
    make_pred(*args)

for args in [
        ("void?", values.w_void),
        ("false?", values.w_false),
        ("null?", cons.w_null),
        ]:
    make_pred_eq(*args)

def make_arith(name, zero, methname):
    @expose(name, simple=True)
    @jit.unroll_safe
    def do(args):
        if not args and zero:
            return zero
        else:
            init = args[0]
            for i in args[1:]:
                init = getattr(init, methname)(i)
            return init

for args in [
        ("+", values.W_Fixnum(0), "arith_add"),
        ("-", None, "arith_sub"),
        ("/", None, "arith_div"),
        ("*", values.W_Fixnum(1), "arith_mul"),
        ]:
    make_arith(*args)

def make_unary_arith(name, methname):
    @expose(name, [values.W_Number], simple=True)
    def do(a):
        return getattr(a, methname)()

for args in [
        ("sin", "arith_sin"),
        ("cos", "arith_cos"),
        ("atan", "arith_atan"),
        ("sqrt", "arith_sqrt"),
        ("sub1", "arith_sub1"),
        ]:
    make_unary_arith(*args)

val("null", cons.w_null)
val("true", values.w_true)
val("false", values.w_false)
val("void", values.w_void)

def equal_loop(a,b):
    if a is b:
        return True
    if isinstance(a, values.W_Fixnum) and isinstance(b, values.W_Fixnum):
        return a.value == b.value
    if a is values.w_void:
        return False
    if a is cons.w_null:
        return False
    if isinstance(a, values.W_Symbol): 
        return False
    if isinstance(a, cons.W_Cons) and isinstance(b, cons.W_Cons):
        return equal_loop(a.car, b.car) and equal_loop(a.cdr, b.cdr)
    if isinstance(a, vec.W_Vector) and isinstance(b, vec.W_Vector):
        if a.length() != b.length(): return False
        for i in range(a.length()):
            if not equal_loop(a.ref(i), b.ref(i)):
                return False
        return True
    return False

@expose("equal?", [values.W_Object] * 2)
def equalp(a, b):
    # this doesn't work for cycles
    return values.W_Bool.make(equal_loop(a,b))

@expose("eq?", [values.W_Object] * 2)
def eqp(a, b):
    # this doesn't work for cycles
    if a is b:
        return values.w_true
    if isinstance(a, values.W_Fixnum) and isinstance(b, values.W_Fixnum):
        return values.W_Bool.make(a.value == b.value)
    else:
        return values.w_false


# ------------------------- List ------------------------

@expose("length", [cons.W_List])
def length(a):
    n = 0
    while True:
        if isinstance(a, cons.W_Null):
            return values.W_Fixnum(n)
        if isinstance(a, cons.W_Cons):
            a = a.cdr
            n = n+1
        else:
            raise SchemeException("length: not a list")
        
# my kingdom for a tail call
def listp_loop(v):
    while True:
        if v is cons.w_null: return True
        if isinstance(v, cons.W_Cons):
            v = v.cdr
            continue
        return False

@expose("list?", [values.W_Object])
def consp(v):
    return values.W_Bool.make(listp_loop(v))

@expose("list")
def do_list(args):
    return cons.to_list(args)

@expose("list*")
def do_liststar(args):
    a = len(args)-1
    if a < 0:
        raise SchemeException("list* expects at least one argument")
    return cons.to_improper(args[:a], args[a])

@expose("assq", [values.W_Object] * 2)
def assq(a, b):
    if cons.w_null is b:
        return values.w_false
    else:
        if eqp([a, do_car([do_car([b])])]):
            return do_car([b])
        else:
            return assq([a, do_cdr([b])])


@expose("cons", [values.W_Object, values.W_Object])
def do_cons(a, b):
    return cons.W_Cons(a,b)

@expose("car", [cons.W_Cons])
def do_car(a):
    return a.car

@expose("cadr")
def do_cadr(args):
    return do_car([do_cdr(args)])

@expose("cddr")
def do_cddr(args):
    return do_cdr([do_cdr(args)])

@expose("caddr")
def do_caddr(args):
    return do_car([do_cdr([do_cdr(args)])])

@expose("cadddr")
def do_cadddr(args):
    return do_car([do_cdr([do_cdr([do_cdr(args)])])])

@expose("cdr", [cons.W_Cons])
def do_cdr(a):
    return a.cdr

@expose("set-car!", [cons.W_Cons, values.W_Object])
def do_set_car(a, b):
    a.car = b

@expose("set-cdr!", [cons.W_Cons, values.W_Object])
def do_set_cdr(a, b):
    a.cdr = b

# ------------------------- Vector ------------------------

@expose("vector-ref")
def vector_ref(args):
    v, i = args
    if not isinstance(v, vec.W_Vector):
        raise SchemeException("vector-ref: expected a vector")
    if not isinstance(i, values.W_Fixnum):
        raise SchemeException("vector-ref: expected a fixnum")
    idx = i.value
    if not (0 <= idx < v.length()):
        raise SchemeException("vector-ref: index out of bounds")
    return v.ref(i.value)

@expose("vector-set!", [vec.W_Vector, values.W_Fixnum, values.W_Object])
def vector_set(v, i, new):
    idx = i.value
    if not (0 <= idx < v.length()):
        raise SchemeException("vector-set!: index out of bounds")
    v.set(i.value, new)

@expose("vector")
def vector(args):
    return vec.W_Vector.fromelements(args)

@expose("make-vector")
def make_vector(args):
    if len(args) == 2:
        n, val = args
    elif len(args) == 1:
        n, = args
        val = values.W_Fixnum(0)
    else:
        raise SchemeException("make-vector: unexpected number of parameters")
    if not isinstance(n, values.W_Fixnum):
        raise SchemeException("make-vector: expected a fixnum")
    if not (n.value >= 0):
        raise SchemeException("make-vector: expected a positive fixnum")
    return vec.W_Vector.fromelement(val, n.value)

@expose("vector-length", [vec.W_Vector])
def vector_length(v):
    return values.W_Fixnum(v.length())


# ------------------------- Other ------------------------

@expose("number->string", [values.W_Number])
def num2str(a):
    return values.W_String(a.tostring())

@expose("call/cc", [proc.W_Procedure], simple=False)
def callcc(a, env, frame):
    return a.call([proc.W_Continuation(frame)], env, frame)

@expose("display", [values.W_Object])
def display(s):
    os.write(1, s.tostring())
    return values.w_void

@expose("write", [values.W_Object])
def write(s):
    os.write(1, s.tostring())
    return values.w_void
