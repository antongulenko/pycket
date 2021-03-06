from rpython.rlib import jit, unroll
from pycket.error import SchemeException

prim_env = {}

class unsafe(object):
    """ can be used in the argtypes part of an @expose call. The corresponding
    argument will be assumed to have the precise corresponding type (no
    subtypes!)."""

    def __init__(self, typ):
        self.typ = typ

class default(object):
    """ can be used in the argtypes part of an @expose call. If the argument is
    missing, the default value is passed to the function. """

    def __init__(self, typ, default=None):
        self.typ = typ
        self.default = default

class procedure(object):
    errorname = "procedure"

def _make_arg_unwrapper(func, argstypes, funcname, has_self=False):
    argtype_tuples = []
    min_arg = 0
    isdefault = False
    for i, typ in enumerate(argstypes):
        isunsafe = False
        default_value = None
        if isinstance(typ, default):
            isdefault = True
            default_value = typ.default
            typ = typ.typ
        else:
            assert not isdefault, "non-default argument %s after default argument" % typ
            min_arg += 1
        if isinstance(typ, unsafe):
            typ = typ.typ
            subclasses = typ.__subclasses__()
            if subclasses:
                raise ValueError("type %s cannot be used unsafely, since it has subclasses %s" % (typ, subclasses))
            isunsafe = True
        argtype_tuples.append((i, typ, isunsafe, isdefault, default_value))
    unroll_argtypes = unroll.unrolling_iterable(argtype_tuples)
    max_arity = len(argstypes)
    if min_arg == max_arity:
        aritystring = max_arity
    else:
        aritystring = "%s to %s" % (min_arg, max_arity)
    errormsg_arity = "expected %s arguments to %s, got %%s" % (
        aritystring, funcname)
    for _, typ, _, _, _ in argtype_tuples:
        assert typ.__dict__.get("errorname"), str(typ)
    _arity = range(min_arg, max_arity+1), -1
    def func_arg_unwrap(*allargs):
        from pycket import values
        if has_self:
            self = allargs[0]
            args = allargs[1]
            rest = allargs[2:]
            typed_args = (self, )
        else:
            args = allargs[0]
            rest = allargs[1:]
            typed_args = ()
        if not min_arg <= len(args) <= max_arity:
            raise SchemeException(errormsg_arity % len(args))
        lenargs = len(args)
        for i, typ, unsafe, default, default_value in unroll_argtypes:
            if i >= min_arg and i >= lenargs:
                assert default
                typed_args += (default_value, )
                continue
            arg = args[i]

            if not unsafe:
                if typ is not values.W_Object and not (
                    typ is procedure and arg.iscallable() or \
                        isinstance(arg, typ)):
                    raise SchemeException(
                        "expected %s as argument to %s, got %s" % (
                            typ.errorname, funcname, arg.tostring()))
            else:
                assert arg is not None
                # the following precise type check is intentional.
                # record_known_class records a precise class to the JIT,
                # excluding subclasses
                assert type(arg) is typ
                jit.record_known_class(arg, typ)
            typed_args += (arg, )
        typed_args += rest
        return func(*typed_args)
    func_arg_unwrap.func_name = "%s_arg_unwrap" % (func.func_name, )
    return func_arg_unwrap, _arity

def _make_result_handling_func(func_arg_unwrap, simple):
    if simple:
        def func_result_handling(*args):
            from pycket.interpreter import (return_multi_vals,
                                            return_value_direct)
            from pycket             import values
            env = args[-2]
            cont = args[-1]
            args = args[:-2]
            result = func_arg_unwrap(*args)
            if result is None:
                result = values.w_void
            if isinstance(result, values.Values):
                return return_multi_vals(result, env, cont)
            else:
                return return_value_direct(result, env, cont)
        return func_result_handling
    else:
        return func_arg_unwrap

# FIXME: Abstract away the common operations between this and expose
def make_procedure(n="<procedure>", argstypes=None, simple=True, arity=None):
    def wrapper(func):
        from pycket import values
        names = [n] if isinstance(n, str) else n
        name = names[0]
        if argstypes is not None:
            func_arg_unwrap, _arity = _make_arg_unwrapper(func, argstypes, name)
            if arity is not None:
                _arity = arity
        else:
            func_arg_unwrap = func
            _arity = arity or ([], 0)
        func_result_handling = _make_result_handling_func(func_arg_unwrap, simple)
        return values.W_Prim(name, func_result_handling, _arity)
    return wrapper

def expose(n, argstypes=None, simple=True, arity=None, nyi=False):
    def wrapper(func):
        from pycket import values
        names = [n] if isinstance(n, str) else n
        name = names[0]
        if nyi:
            def func_arg_unwrap(*args):
                raise SchemeException(
                    "primitive %s is not yet implemented" % name)
            _arity = arity or ([], 0)
        elif argstypes is not None:
            func_arg_unwrap, _arity = _make_arg_unwrapper(func, argstypes, name)
            if arity is not None:
                _arity = arity
        else:
            func_arg_unwrap = func
            _arity = arity or ([], 0)
        func_result_handling = _make_result_handling_func(func_arg_unwrap, simple)
        cls = values.W_Prim
        p = cls(name, func_result_handling, _arity)
        for nam in names:
            sym = values.W_Symbol.make(nam)
            if sym in prim_env:
                raise SchemeException("name %s already defined" % nam)
            prim_env[sym] = p
        return func_arg_unwrap
    return wrapper

def make_call_method(argstypes=None, arity=None, simple=True, name="<method>"):
    def wrapper(func):
        if argstypes is not None:
            func_arg_unwrap, _ = _make_arg_unwrapper(
                func, argstypes, name, has_self=True)
        else:
            func_arg_unwrap = func
        return _make_result_handling_func(func_arg_unwrap, simple)
    return wrapper

# Facility to convert a label into a callable object
def make_callable_label(argstypes=None, arity=None, name="<label>"):
    from pycket import values
    class LabelFunction(values.W_Procedure):
        _immutable_fields_ = ["label"]
        def __init__(self, label):
            self.label = label

        @make_call_method(argstypes=argstypes, arity=arity, simple=False)
        def call(self, *rest):
            return self.label(*rest)

        def tostring(self):
            return "#<procedure>"

    def wrapper(label):
        return LabelFunction(label)

    return wrapper


def expose_val(name, w_v):
    from pycket import values
    sym = values.W_Symbol.make(name)
    if sym in prim_env:
        raise Error("name %s already defined" % name)
    prim_env[sym] = w_v

def define_nyi(name, prim_args=None, *args, **kwargs):
    @expose(name, prim_args, nyi=True, *args, **kwargs)
    def nyi(a):
        pass
