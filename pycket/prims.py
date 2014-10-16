#! /usr/bin/env python
# -*- coding: utf-8 -*-
import operator
import os
import time
import math
import pycket.impersonators as imp
from rpython.rlib.rbigint import rbigint
from pycket import values
from pycket.cont import Cont, continuation, label, call_cont
from pycket import cont
from pycket import values_struct
from pycket import vector as values_vector
from pycket.exposeprim import unsafe, default, expose, expose_val, procedure
from pycket import arithmetic # imported for side effect
from pycket.error import SchemeException
from rpython.rlib  import jit

prim_env = {}

def make_cmp(name, op, con):
    from values import W_Number, W_Fixnum, W_Flonum, W_Bignum
    from rpython.rlib.rbigint import rbigint
    @expose(name, [W_Number, W_Number], simple=True)
    def do(w_a, w_b):
        if isinstance(w_a, W_Fixnum) and isinstance(w_b, W_Fixnum):
            return con(getattr(operator, op)(w_a.value, w_b.value))
        if isinstance(w_a, W_Bignum) and isinstance(w_b, W_Bignum):
            return con(getattr(w_a.value, op)(w_b.value))
        if isinstance(w_a, W_Flonum) and isinstance(w_b, W_Flonum):
            return con(getattr(operator, op)(w_a.value, w_b.value))

        # Upcast float
        if isinstance(w_a, W_Fixnum) and isinstance(w_b, W_Flonum):
            a = float(w_a.value)
            return con(getattr(operator, op)(a, w_b.value))
        if isinstance(w_a, W_Flonum) and isinstance(w_b, W_Fixnum):
            b = float(w_b.value)
            return con(getattr(operator, op)(w_a.value, b))

        # Upcast bignum
        if isinstance(w_a, W_Bignum) and isinstance(w_b, W_Fixnum):
            b = rbigint.fromint(w_b.value)
            return con(getattr(w_a.value, op)(b))
        if isinstance(w_a, W_Fixnum) and isinstance(w_b, W_Bignum):
            a = rbigint.fromint(w_a.value)
            return con(getattr(a, op)(w_b.value))

        # Upcast bignum/float
        if isinstance(w_a, W_Bignum) and isinstance(w_b, W_Flonum):
            b = rbigint.fromfloat(w_b.value)
            return con(getattr(w_a.value, op)(b))
        if isinstance(w_a, W_Flonum) and isinstance(w_b, W_Bignum):
            a = rbigint.fromfloat(w_a.value)
            return con(getattr(a, op)(w_b.value))

        raise SchemeException("unsupported operation %s on %s %s" % (
            name, w_a.tostring(), w_b.tostring()))
    do.__name__ = op

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
    def predicate_(a):
        return values.W_Bool.make(isinstance(a, cls))
    predicate_.__name__ +=  cls.__name__

def make_pred_eq(name, val):
    typ = type(val)
    @expose(name, [values.W_Object], simple=True)
    def pred_eq(a):
        return values.W_Bool.make(isinstance(a, typ) and a is val)

for args in [
        ("pair?", values.W_Cons),
        ("mpair?", values.W_MCons),
        ("number?", values.W_Number),
        ("complex?", values.W_Number),
        ("fixnum?", values.W_Fixnum),
        ("flonum?", values.W_Flonum),
        ("vector?", values.W_MVector),
        ("string?", values.W_String),
        ("symbol?", values.W_Symbol),
        ("boolean?", values.W_Bool),
        ("inspector?", values_struct.W_StructInspector),
        ("struct-type?", values_struct.W_StructType),
        ("struct-constructor-procedure?", values_struct.W_StructConstructor),
        ("struct-predicate-procedure?", values_struct.W_StructPredicate),
        ("struct-accessor-procedure?", values_struct.W_StructAccessor),
        ("struct-mutator-procedure?", values_struct.W_StructMutator),
        ("struct-type-property?", values_struct.W_StructProperty),
        ("struct-type-property-accessor-procedure?", values_struct.W_StructPropertyAccessor),
        ("box?", values.W_Box),
        ("regexp?", values.W_Regexp),
        ("pregexp?", values.W_PRegexp),
        ("byte-regexp?", values.W_ByteRegexp),
        ("byte-pregexp?", values.W_BytePRegexp),
        ("variable-reference?", values.W_VariableReference),
        ("syntax?", values.W_Syntax),
        ("thread-cell?", values.W_ThreadCell),
        ("thread-cell-values?", values.W_ThreadCellValues),
        ("semaphore?", values.W_Semaphore),
        ("semaphore-peek-evt?", values.W_SemaphorePeekEvt),
        ("path?", values.W_Path),
        ("arity-at-least?", values.W_ArityAtLeast),
        ("bytes?", values.W_Bytes),
        ("pseudo-random-generator?", values.W_PseudoRandomGenerator),
        ("char?", values.W_Character),
        ("continuation?", values.W_Continuation),
        ("continuation-mark-set?", values.W_ContinuationMarkSet),
        ("primitive?", values.W_Prim),
        ("keyword?", values.W_Keyword),
        ("weak-box?", values.W_WeakBox),
        ("ephemeron?", values.W_Ephemeron),
        ("placeholder?", values.W_Placeholder),
        ("hash-placeholder?", values.W_HashTablePlaceholder),
        ("module-path-index?", values.W_ModulePathIndex),
        ("resolved-module-path?", values.W_ResolvedModulePath),
        ("impersonator-property-accessor-procedure?", imp.W_ImpPropertyAccessor),
        # FIXME: Assumes we only have eq-hashes
        ("hash?", values.W_HashTable),
        ("hash-eq?", values.W_HashTable),
        ("hash-eqv?", values.W_HashTable),
        ("hash-equal?", values.W_HashTable),
        ("hash-weak?", values.W_HashTable)
        ]:
    make_pred(*args)

for args in [
        ("void?", values.w_void),
        ("false?", values.w_false),
        ("null?", values.w_null),
        ]:
    make_pred_eq(*args)

@expose("byte?", [values.W_Object])
def byte_huh(val):
    if isinstance(val, values.W_Fixnum):
        return values.W_Bool.make(0 <= val.value <= 255)
    if isinstance(val, values.W_Bignum):
        try:
            v = val.value.toint()
            return values.W_Bool.make(0 <= v <= 255)
        except OverflowError:
            return values.w_false
    return values.w_false

@expose("procedure?", [values.W_Object])
def procedurep(n):
    return values.W_Bool.make(n.iscallable())

@expose("integer?", [values.W_Object])
def integerp(n):
    return values.W_Bool.make(isinstance(n, values.W_Fixnum) or
                              isinstance(n, values.W_Bignum) or
                              isinstance(n, values.W_Flonum) and
                              math.floor(n.value) == n.value)


@expose("exact-integer?", [values.W_Object])
def exact_integerp(n):
    return values.W_Bool.make(isinstance(n, values.W_Fixnum) or
                              isinstance(n, values.W_Bignum))

@expose("exact-nonnegative-integer?", [values.W_Object])
def exact_nonneg_integerp(n):
    from rpython.rlib.rbigint import rbigint
    if isinstance(n, values.W_Fixnum):
        return values.W_Bool.make(n.value >= 0)
    if isinstance(n, values.W_Bignum):
        return values.W_Bool.make(n.value.ge(rbigint.fromint(0)))
    return values.w_false

@expose("exact-positive-integer?", [values.W_Object])
def exact_nonneg_integerp(n):
    from rpython.rlib.rbigint import rbigint
    if isinstance(n, values.W_Fixnum):
        return values.W_Bool.make(n.value > 0)
    if isinstance(n, values.W_Bignum):
        return values.W_Bool.make(n.value.gt(rbigint.fromint(0)))
    return values.w_false

@expose("real?", [values.W_Object])
def realp(n):
    return values.W_Bool.make(isinstance(n, values.W_Fixnum) or
                              isinstance(n, values.W_Bignum) or
                              isinstance(n, values.W_Flonum))

@expose("inexact-real?", [values.W_Object])
def inexact_real(n):
    return values.W_Bool.make(isinstance(n, values.W_Flonum))

@expose("single-flonum?", [values.W_Object])
def single_flonum(n):
    return values.w_false

@expose("double-flonum?", [values.W_Object])
def double_flonum(n):
    return values.W_Bool.make(isinstance(n, values.W_Flonum))

@expose("syntax-original?", [values.W_Syntax])
def syntax_original(v):
    return values.w_false

@expose("syntax-tainted?", [values.W_Syntax])
def syntax_tainted(v):
    return values.w_false

@expose("compiled-module-expression?", [values.W_Object])
def compiled_module_expression(v):
    return values.w_false

@expose("rational?", [values.W_Object])
def rationalp(n):
    if isinstance(n, values.W_Fixnum) or isinstance(n, values.W_Bignum):
        return values.w_true
    if isinstance(n, values.W_Flonum):
        v = n.value
        return values.W_Bool.make(not(math.isnan(v) or math.isinf(v)))

@expose("exact?", [values.W_Object])
def exactp(n):
    return values.W_Bool.make(isinstance(n, values.W_Fixnum) or
                              isinstance(n, values.W_Bignum))

@expose("inexact?", [values.W_Object])
def inexactp(n):
    return values.W_Bool.make(isinstance(n, values.W_Flonum))


@expose("quotient/remainder", [values.W_Integer, values.W_Integer])
def quotient_remainder(a, b):
    return values.Values.make([a.arith_quotient(b), values.W_Fixnum(0)])


def make_binary_arith(name, methname):
    @expose(name, [values.W_Number, values.W_Number], simple=True)
    def do(a, b):
        return getattr(a, methname)(b)
    do.__name__ = methname

for args in [
        ("quotient", "arith_quotient"),
        ("modulo",   "arith_mod"),
        ("expt",     "arith_pow"),
        ("max",      "arith_max"),
        ("min",      "arith_min"),
        ]:
    make_binary_arith(*args)


def make_arith(name, neutral_element, methname, supports_zero_args):
    @expose(name, simple=True)
    @jit.unroll_safe
    def do(args):
        if not args:
            if not supports_zero_args:
                raise SchemeException("expected at least 1 argument to %s" % name)
            return neutral_element
        if len(args) == 1:
            return getattr(neutral_element, methname)(args[0])
        else:
            init = args[0]
            for i in range(1, jit.promote(len(args))):
                init = getattr(init, methname)(args[i])
            return init
    do.__name__ = methname

for args in [
        ("+", values.W_Fixnum(0), "arith_add", True),
        ("-", values.W_Fixnum(0), "arith_sub", False),
        ("*", values.W_Fixnum(1), "arith_mul", True),
        ("/", values.W_Fixnum(1), "arith_div", False),
        ("bitwise-and", values.W_Fixnum(-1), "arith_and", True),
        ("bitwise-ior", values.W_Fixnum(0), "arith_or", True),
        ("bitwise-xor", values.W_Fixnum(0), "arith_xor", True),
        ]:
    make_arith(*args)

def make_unary_arith(name, methname):
    @expose(name, [values.W_Number], simple=True)
    def do(a):
        return getattr(a, methname)()
    do.__name__ = methname

@expose("add1", [values.W_Number])
def add1(v):
    return v.arith_add(values.W_Fixnum(1))

for args in [
        ("sin", "arith_sin"),
        ("cos", "arith_cos"),
        ("atan", "arith_atan"),
        ("sqrt", "arith_sqrt"),
        ("sub1", "arith_sub1"),
        ("exact->inexact", "arith_exact_inexact"),
        ("zero?", "arith_zerop"),
        ("negative?", "arith_negativep"),
        ("positive?", "arith_positivep"),
        ("even?", "arith_evenp"),
        ("odd?", "arith_oddp"),
        ("abs", "arith_abs")
        ]:
    make_unary_arith(*args)


expose_val("null", values.w_null)
expose_val("true", values.w_true)
expose_val("false", values.w_false)
expose_val("exception-handler-key", values.exn_handler_key)
expose_val("parameterization-key", values.parameterization_key)

# FIXME: need stronger guards for all of these
for name in ["prop:evt",
             "prop:output-port",
             "prop:impersonator-of",
             "prop:method-arity-error"]:
    expose_val(name, values_struct.W_StructProperty(values.W_Symbol.make(name), values.w_false))

expose_val("prop:procedure", values_struct.w_prop_procedure)
expose_val("prop:checked-procedure", values_struct.w_prop_checked_procedure)
expose_val("prop:arity-string", values_struct.w_prop_arity_string)
expose_val("prop:custom-write", values_struct.w_prop_custom_write)
expose_val("prop:equal+hash", values_struct.w_prop_equal_hash)

@continuation
def check_cont(proc, v, v1, v2, env, cont, _vals):
    from pycket.interpreter import check_one_val, return_value
    val = check_one_val(_vals)
    if val is not values.w_false:
        return return_value(v._ref(1), env, cont)
    return proc.call([v, v1, v2], env, cont)

@continuation
def receive_first_field(proc, v, v1, v2, env, cont, _vals):
    from pycket.interpreter import check_one_val
    first_field = check_one_val(_vals)
    return first_field.call([v1, v2], env, check_cont(proc, v, v1, v2, env, cont))

@expose("checked-procedure-check-and-extract",
        [values_struct.W_StructType, values.W_Object, procedure,
         values.W_Object, values.W_Object], simple=False)
def do_checked_procedure_check_and_extract(type, v, proc, v1, v2, env, cont):
    if isinstance(v, values_struct.W_Struct):
        st = v.struct_type()
        if st is type:
            return v.ref(v.struct_type(), 0, env,
                    receive_first_field(proc, v, v1, v2, env, cont))
    return proc.call([v, v1, v2], env, cont)

################################################################
# printing

@expose("display", [values.W_Object])
def display(s):
    os.write(1, s.tostring())
    return values.w_void

@expose("newline", [])
def newline():
    os.write(1, "\n")

@expose("write", [values.W_Object])
def write(s):
    os.write(1, s.tostring())

@expose("print", [values.W_Object])
def do_print(o):
    os.write(1, o.tostring())

class OutputFormatter(object):
    def __init__(self, replacements):
        self.replacements = replacements
    def format(self, text):
        for key, value in self.replacements.iteritems():
            result = []
            pos = 0
            while True:
                match = text.find(key, pos)
                if match > 0:
                    result.append(text[pos : match])
                    result.append(value)
                    pos = match + len(key)
                else:
                    result.append(text[pos:])
                    break
            text = "".join(result)
        return text

@expose("fprintf", [values.W_OutputPort, values.W_String, values.W_Object])
def do_fprintf(out, form, v):
    # FIXME: it should print formatted output to _out_
    replacements = {
        '~n': '\n',
        '~%': '\n',
        '~a': v.tostring()}
    formatter = OutputFormatter(replacements)
    os.write(1, formatter.format(form.tostring()))

def cur_print_proc(args):
    v, = args
    if v is not values.w_void:
        os.write(1, v.tostring())
        os.write(1, "\n")
    return values.w_void

@expose("open-output-string", [])
def open_output_string():
    return values.W_StringOutputPort()

@expose("port-display-handler", [values.W_OutputPort])
def port_display_handler(p):
    return values.W_SimplePrim("pretty-printer", cur_print_proc)

@expose("port-write-handler", [values.W_OutputPort])
def port_write_handler(p):
    return values.W_SimplePrim("pretty-printer", cur_print_proc)

# FIXME: this is a parameter
@expose("current-print", [])
def current_print():
    return values.W_SimplePrim("pretty-printer", cur_print_proc)

@expose("current-logger", [])
def current_logger():
    return values.current_logger

@expose("make-logger", [values.W_Symbol, values.W_Logger])
def make_logger(name, parent):
    return values.W_Logger()

@expose("make-weak-hasheq", [])
def make_weak_hasheq():
    # FIXME: not actually weak
    return values.W_HashTable([], [])

@expose("make-parameter", [values.W_Object, default(values.W_Object, values.w_false)])
def make_parameter(init, guard):
    return values.W_Parameter(init, guard)

@expose("system-library-subpath", [default(values.W_Object, values.w_false)])
def sys_lib_subpath(mode):
    return values.W_Path("x86_64-linux") # FIXME

@expose("primitive-closure?", [values.W_Object])
def prim_clos(v):
    return values.w_false

################################################################
# String stuff

# FIXME: this implementation sucks
@expose("string-append")
def string_append(args):
    if not args:
        return values.W_String("")
    l = []
    for a in args:
        if not isinstance(a, values.W_String):
            raise SchemeException("string-append: expected a string")
        l.append(a.value)
    return values.W_String(''.join(l))

@expose("string-length", [values.W_String])
def string_length(s1):
    return values.W_Fixnum(len(s1.value))

@expose("substring", [values.W_String, values.W_Fixnum, default(values.W_Fixnum, None)])
def substring(w_string, w_start, w_end):
    """
    (substring str start [end]) → string?
        str : string?
        start : exact-nonnegative-integer?
        end : exact-nonnegative-integer? = (string-length str)
    """
    string = w_string.value
    start = w_start.value
    if start > len(string) or start < 0:
        raise SchemeException("substring: end index out of bounds")
    if w_end is not None:
        end = w_end.value
        if end > len(string) or end < 0:
            raise SchemeException("substring: end index out of bounds")
    else:
        end = len(string)
    if end < start:
        raise SchemeException(
            "substring: ending index is smaller than starting index")
    return values.W_String(string[start:end])

@expose("string-ref", [values.W_String, values.W_Fixnum])
def string_ref(s, n):
    idx = n.value
    st  = s.value
    if idx < 0 or idx >= len(st):
        raise SchemeException("string-ref: index out of range")
    return values.W_Character(st[idx])

@expose("string=?", [values.W_String, values.W_String])
def string_equal(s1, s2):
    v1 = s1.value
    v2 = s2.value
    if len(v1) != len(v2):
        return values.w_false
    for i in range(len(v1)):
        if v1[i] != v2[i]:
            return values.w_false
    return values.w_true

@expose("string<?", [values.W_String, values.W_String])
def string_lt(s1, s2):
    v1 = s1.value
    v2 = s2.value
    for i in range(len(v1)):
        if v1[i] < v2[i]:
            return values.w_false
    return values.w_true

@expose("char->integer", [values.W_Character])
def char2int(c):
    return values.W_Fixnum(ord(c.value))

################################################################
# build-in exception types

def define_exn(name, super=values.w_null, fields=[]):
    exn_type, exn_constr, exn_pred, exn_acc, exn_mut = \
        values_struct.W_StructType.make(values.W_Symbol.make(name), super,
        values.W_Fixnum(len(fields)), values.W_Fixnum(0), values.w_false,
        values.w_null, values.w_false).make_struct_tuple()
    expose_val("struct:" + name, exn_type)
    expose_val(name, exn_constr)
    expose_val(name + "?", exn_pred)
    for field, field_name in enumerate(fields):
        acc = values_struct.W_StructFieldAccessor(exn_acc, values.W_Fixnum(field), values.W_Symbol.make(field_name))
        expose_val(name + "-" + field_name, acc)
    return exn_type

exn = define_exn("exn", values.w_null, ["message", "continuation-marks"])
exn_fail = define_exn("exn:fail", exn)
exn_fail_contract = define_exn("exn:fail:contract", exn_fail)
exn_fail_contract_arity = define_exn("exn:fail:contract:arity", exn_fail)
exn_fail_contract_divide_by_zero = define_exn("exn:fail:contract:divide-by-zero", exn_fail)
exn_fail_contract_non_fixnum_result = define_exn("exn:fail:contract:non-fixnum-result", exn_fail)
exn_fail_contract_continuation = define_exn("exn:fail:contract:continuation", exn_fail)
exn_fail_contract_variable = define_exn("exn:fail:contract:variable", exn_fail, ["id"])
exn_fail_syntax = define_exn("exn:fail:syntax", exn_fail, ["exprs"])
exn_fail_syntax_unbound = define_exn("exn:fail:syntax:unbound", exn_fail_syntax)
exn_fail_syntax_missing_module = define_exn("exn:fail:syntax:missing-module", exn_fail_syntax, ["path"])
exn_fail_read = define_exn("exn:fail:read", exn_fail, ["srclocs"])
exn_fail_read_eof = define_exn("exn:fail:read:eof", exn_fail_read)
exn_fail_read_non_char = define_exn("exn:fail:read:non-char", exn_fail_read)
exn_fail_fs = define_exn("exn:fail:filesystem", exn_fail)
exn_fail_fs_exists = define_exn("exn:fail:filesystem:exists", exn_fail_fs)
exn_fail_fs_version = define_exn("exn:fail:filesystem:version", exn_fail_fs)
exn_fail_fs_errno = define_exn("exn:fail:filesystem:errno", exn_fail_fs, ["errno"])
exn_fail_fs_missing_module = define_exn("exn:fail:filesystem:missing-module", exn_fail_fs, ["path"])
exn_fail_network = define_exn("exn:fail:network", exn_fail)
exn_fail_network_errno = define_exn("exn:fail:network:errno", exn_fail_network, ["errno"])
exn_fail_out_of_memory = define_exn("exn:fail:out-of-memory", exn_fail)
exn_fail_unsupported = define_exn("exn:fail:unsupported", exn_fail)
exn_fail_user = define_exn("exn:fail:user", exn_fail)
exn_break = define_exn("exn:break", exn)
exn_break_hang_up = define_exn("exn:break:hang-up", exn_break)
exn_break_terminate = define_exn("exn:break:terminate", exn_break)


def define_nyi(name, args=None):
    @expose(name, args, nyi=True)
    def nyi(args): pass

for args in [ ("date",),
              ("date*",),
              ("srcloc",),
              ("subprocess?",),
              ("input-port?",),

              ("output-port?",),
              ("file-stream-port?",),
              ("terminal-port?",),
              ("port-closed?",),
              ("port-provides-progress-evts?",),
              ("port-writes-atomic?",),
              ("port-writes-special?",),
              ("byte-ready?",),
              ("char-ready?",),
              ("eof-object?",),
              ("bytes-converter?",),
              ("char-alphabetic?",),
              ("char-numeric?",),
              ("char-symbolic?",),
              ("char-graphic?",),
              ("char-whitespace?",),
              ("char-blank?",),
              ("char-iso-control?",),
              ("char-punctuation?",),
              ("char-upper-case?",),
              ("char-title-case?",),
              ("char-lower-case?",),
              ("compiled-expression?",),
              ("custom-write?",),
              ("custom-print-quotable?",),
              ("liberal-define-context?",),
              ("handle-evt?",),
              ("procedure-struct-type?",),
              ("special-comment?",),
              ("exn:srclocs?",),
              ("impersonator-property?",),
              ("logger?",),
              ("log-receiver?",),
              # FIXME: these need to be defined with structs
              ("date?",),
              ("date-dst?",),
              ("date*?",),
              ("srcloc?",),
              ("thread?",),
              ("thread-running?",),
              ("thread-dead?",),
              ("custodian?",),
              ("custodian-box?",),
              ("namespace?",),
              ("security-guard?",),
              ("thread-group?",),
              ("parameter?",),
              ("parameterization?",),
              ("will-executor?",),
              ("evt?",),
              ("semaphore-try-wait?",),
              ("channel?",),
              ("readtable?",),
              ("path-for-some-system?",),
              ("file-exists?",),
              ("directory-exists?",),
              ("link-exists?",),
              ("relative-path?",),
              ("absolute-path?",),
              ("complete-path?",),
              ("internal-definition-context?",),
              ("set!-transformer?",),
              ("rename-transformer?",),
              ("path-string?",),
              ("identifier?",),
              ("port?",),
              ("sequence?",),
              ("namespace-anchor?",),
              ("chaperone-channel",),
              ("impersonate-channel",),

              ("string-ci<?", [values.W_String, values.W_String]),
              ("keyword<?", [values.W_Keyword, values.W_Keyword]),
              ("string-ci<=?", [values.W_String, values.W_String])
]:
    define_nyi(*args)

@expose("object-name", [values.W_Object])
def object_name(v):
    return values.W_String(v.tostring())

@expose("find-main-config", [])
def find_main_config():
    return values.w_false

@expose("version", [])
def version():
    from pycket import interpreter
    version = interpreter.GlobalConfig.lookup("version")
    return values.W_String("unknown version" if version is None else version)

@continuation
def sem_post_cont(sem, env, cont, vals):
    sem.post()
    from interpreter import return_multi_vals
    return return_multi_vals(vals, env, cont)

@expose("call-with-semaphore", simple=False)
def call_with_sem(args, env, cont):
    if len(args) < 2:
        raise SchemeException("error call-with-semaphore")
    sem = args[0]
    f = args[1]
    if len(args) == 2:
        new_args = []
        fail = None
    else:
        new_args = args[3:]
        if args[2] is values.w_false:
            fail = None
        else:
            fail = args[2]
    assert isinstance(sem, values.W_Semaphore)
    assert f.iscallable()
    sem.wait()
    return f.call(new_args, env, sem_post_cont(sem, env, cont))

@expose("current-thread", [])
def current_thread():
    return values.W_Thread()

@expose("semaphore-post", [values.W_Semaphore])
def sem_post(s):
    s.post()

@expose("semaphore-wait", [values.W_Semaphore])
def sem_wait(s):
    s.wait()

@expose("arity-at-least", [values.W_Fixnum])
def arity_at_least(n):
    return values.W_ArityAtLeast(n.value)

@expose("arity-at-least-value", [values.W_ArityAtLeast])
def arity_at_least(a):
    return values.W_Fixnum(a.val)

@expose("procedure-rename", [procedure, values.W_Object])
def procedure_rename(p, n):
    return p

@expose("procedure-arity", [procedure])
def arity_at_least(n):
    # FIXME
    return values.W_ArityAtLeast(0)

@expose("procedure-arity?", [values.W_Object])
def arity_at_least_p(n):
    if isinstance(n, values.W_Fixnum):
        if n.value >= 0:
            return values.w_true
    elif isinstance(n, values.W_ArityAtLeast):
        return values.w_true
    elif isinstance(n, values.W_List):
        for item in values.from_list(n):
            if not (isinstance(item, values.W_Fixnum) or isinstance(item, values.W_ArityAtLeast)):
                return values.w_false
        return values.w_true
    return values.w_false

@expose("string<=?", [values.W_String, values.W_String])
def string_le(s1, s2):
    v1 = s1.value
    v2 = s2.value
    for i in range(len(v1)):
        if v1[i] <= v2[i]:
            return values.w_false
    return values.w_true

@expose("make-string", [values.W_Fixnum, default(values.W_Character, values.w_null)])
def string_to_list(k, char):
    char = str(char.value) if isinstance(char, values.W_Character) else '\0'
    return values.W_String(char * k.value)

@expose("string->list", [values.W_String])
def string_to_list(s):
    return values.to_list([values.W_Character(i) for i in s.value])

@expose("procedure-arity-includes?", [procedure, values.W_Number])
def procedure_arity_includes(p, n):
    if not(isinstance(n, values.W_Fixnum)):
        return values.w_false # valid arities are always small integers
    n_val = n.value
    (ls, at_least) = p.get_arity()
    for i in ls:
        if n_val == i: return values.w_true
    if at_least != -1 and n_val >= at_least:
        return values.w_true
    return values.w_false

@expose("variable-reference-constant?", [values.W_VariableReference], simple=False)
def varref_const(varref, env, cont):
    from interpreter import return_value
    return return_value(values.W_Bool.make(not(varref.varref.is_mutable(env))), env, cont)

@expose("variable-reference->resolved-module-path",  [values.W_VariableReference])
def varref_rmp(varref):
    return values.W_ResolvedModulePath(values.W_Path(varref.varref.path))

@expose("resolved-module-path-name", [values.W_ResolvedModulePath])
def rmp_name(rmp):
    return rmp.name

@expose("module-path?", [values.W_Object])
def module_pathp(v):
    if isinstance(v, values.W_Symbol):
        # FIXME: not always right
        return values.w_true
    if isinstance(v, values.W_Path):
        return values.w_true
    # FIXME
    return values.w_false

@expose("values")
def do_values(args_w):
    return values.Values.make(args_w)

@expose("call-with-values", [procedure] * 2, simple=False)
def call_with_values (producer, consumer, env, cont):
    # FIXME: check arity
    return producer.call([], env, call_cont(consumer, env, cont))

@continuation
def time_apply_cont(initial, env, cont, vals):
    from pycket.interpreter import return_multi_vals
    final = time.clock()
    ms = values.W_Fixnum(int((final - initial) * 1000))
    vals_l = vals._get_full_list()
    results = values.Values.make([values.to_list(vals_l), ms, ms, values.W_Fixnum(0)])
    return return_multi_vals(results, env, cont)

@expose("continuation-prompt-available?")
def cont_prompt_avail(args):
    return values.w_false

# FIXME: this is a data type
@expose("continuation-prompt-tag?")
def cont_prompt_tag(args):
    return values.w_false

@expose(["call/cc", "call-with-current-continuation",
         "call/ec", "call-with-escape-continuation"],
        [procedure], simple=False)
def callcc(a, env, cont):
    return a.call([values.W_Continuation(cont)], env, cont)

@expose("time-apply", [procedure, values.W_List], simple=False)
def time_apply(a, args, env, cont):
    initial = time.clock()
    return a.call(values.from_list(args), env, time_apply_cont(initial, env, cont))

@expose("apply", simple=False)
def apply(args, env, cont):
    if not args:
        raise SchemeException("apply expected at least one argument, got 0")
    fn = args[0]
    if not fn.iscallable():
        raise SchemeException("apply expected a procedure, got something else")
    lst = args[-1]
    if not listp_loop(lst):
        raise SchemeException("apply expected a list as the last argument, got something else")
    args_len = len(args)-1
    assert args_len >= 0
    others = args[1:args_len]
    new_args = others + values.from_list(lst)
    return fn.call(new_args, env, cont)

@expose("make-semaphore", [default(values.W_Fixnum, values.W_Fixnum(0))])
def make_semaphore(n):
    return values.W_Semaphore(n.value)

@expose("semaphore-peek-evt", [values.W_Semaphore])
def sem_peek_evt(s):
    return values.W_SemaphorePeekEvt(s)

@expose("printf")
def printf(args):
    if not args:
        raise SchemeException("printf expected at least one argument, got 0")
    fmt = args[0]
    if not isinstance(fmt, values.W_String):
        raise SchemeException("printf expected a format string, got something else")
    fmt = fmt.value
    vals = args[1:]
    i = 0
    j = 0
    while i < len(fmt):
        if fmt[i] == '~':
            if i+1 == len(fmt):
                raise SchemeException("bad format string")
            s = fmt[i+1]
            if s == 'a' or s == 'v' or s == 's':
                # print a value
                # FIXME: different format chars
                if j >= len(vals):
                    raise SchemeException("not enough arguments for format string")
                os.write(1, vals[j].tostring())
                j += 1
            elif s == 'n':
                os.write(1,"\n") # newline
            else:
                raise SchemeException("unexpected format character")
            i += 2
        else:
            os.write(1,fmt[i])
            i += 1

@expose("eqv?", [values.W_Object] * 2)
def eqvp(a, b):
    return values.W_Bool.make(a.eqv(b))

@expose("equal?", [values.W_Object] * 2, simple=False)
def equalp(a, b, env, cont):
    # FIXME: broken for cycles, etc
    return equal_cont(a, b, env, cont)

@expose("equal?/recur", [values.W_Object, values.W_Object, procedure])
def eqp_recur(v1, v2, recur_proc):
    # TODO:
    return values.w_void

@continuation
def equal_car_cont(a, b, env, cont, _vals):
    from pycket.interpreter import check_one_val, return_value
    eq = check_one_val(_vals)
    if eq is values.w_false:
        return return_value(values.w_false, env, cont)
    return equal_cont(a, b, env, cont)

@continuation
def equal_unbox_right_cont(r, env, cont, _vals):
    from pycket.interpreter import check_one_val
    l = check_one_val(_vals)
    return r.unbox(env, equal_unbox_done_cont(l, env, cont))

@continuation
def equal_unbox_done_cont(l, env, cont, _vals):
    from pycket.interpreter import check_one_val
    r = check_one_val(_vals)
    return equal_cont(l, r, env, cont)

# This function assumes that a and b have the same length
@label
def equal_vec_func(a, b, idx, env, cont):
    from pycket.interpreter import return_value
    if idx.value >= a.length():
        return return_value(values.w_true, env, cont)
    return a.vector_ref(idx, env, equal_vec_left_cont(a, b, idx, env, cont))

# Receive the first value for a given index
@continuation
def equal_vec_left_cont(a, b, idx, env, cont, _vals):
    from pycket.interpreter import check_one_val
    l = check_one_val(_vals)
    return b.vector_ref(idx, env,
                equal_vec_right_cont(a, b, idx, l, env, cont))

# Receive the second value for a given index
@continuation
def equal_vec_right_cont(a, b, idx, l, env, cont, _vals):
    from pycket.interpreter import check_one_val
    r = check_one_val(_vals)
    return equal_cont(l, r, env, equal_vec_done_cont(a, b, idx, env, cont))

# Receive the comparison of the two elements and decide what to do
@continuation
def equal_vec_done_cont(a, b, idx, env, cont, _vals):
    from pycket.interpreter import check_one_val, return_value
    eq = check_one_val(_vals)
    if eq is values.w_false:
        return return_value(values.w_false, env, cont)
    inc = values.W_Fixnum(idx.value + 1)
    return equal_vec_func(a, b, inc, env, cont)

# This is needed to be able to drop out of the current stack frame,
# as direct recursive calls to equal will blow out the stack.
# This lets us 'return' before invoking equal on the next pair of
# items.
@label
def equal_cont(a, b, env, cont):
    from pycket.interpreter import return_value
    if imp.is_impersonator_of(a, b) or imp.is_impersonator_of(b, a):
        return return_value(values.w_true, env, cont)
    if isinstance(a, values.W_String) and isinstance(b, values.W_String):
        return return_value(values.W_Bool.make(a.value == b.value), env, cont)
    if isinstance(a, values.W_Cons) and isinstance(b, values.W_Cons):
        return equal_cont(a.car(), b.car(), env,
                    equal_car_cont(a.cdr(), b.cdr(), env, cont))
    if isinstance(a, values.W_Box) and isinstance(b, values.W_Box):
        return a.unbox(env, equal_unbox_right_cont(b, env, cont))
    if isinstance(a, values.W_MVector) and isinstance(b, values.W_MVector):
        if a.length() != b.length():
            return return_value(values.w_false, env, cont)
        return equal_vec_func(a, b, values.W_Fixnum(0), env, cont)
    if isinstance(a, values_struct.W_RootStruct) and isinstance(b, values_struct.W_RootStruct):
        if not a.eqv(b):
            for w_car, w_prop in a.struct_type().props:
                if w_car.isinstance(values_struct.w_prop_equal_hash):
                    for w_car, w_prop in b.struct_type().props:
                        if w_car.isinstance(values_struct.w_prop_equal_hash):
                            assert isinstance(w_prop, values_vector.W_Vector)
                            w_equal_proc, w_hash_proc, w_hash2_proc = \
                                w_prop.ref(0), w_prop.ref(1), w_prop.ref(2)
                            # FIXME: it should work with cycles properly and be an equal?-recur
                            w_equal_recur = values.W_Prim("equal?-recur", equalp)
                            return w_equal_proc.call([a, b, w_equal_recur], env, cont)
            if not a.struct_type().isopaque and not b.struct_type().isopaque:
                l = struct2vector(a)
                r = struct2vector(b)
                return equal_cont(l, r, env, cont)
        else:
            return return_value(values.w_true, env, cont)

    return return_value(values.W_Bool.make(a.eqv(b)), env, cont)

def eqp_logic(a, b):
    if a is b:
        return True
    elif isinstance(a, values.W_Fixnum) and isinstance(b, values.W_Fixnum):
        return a.value == b.value
    elif isinstance(a, values.W_Character) and isinstance(b, values.W_Character):
        return a.value == b.value
    return False

@expose("eq?", [values.W_Object] * 2)
def eqp(a, b):
    return values.W_Bool.make(eqp_logic(a, b))

@expose("not", [values.W_Object])
def notp(a):
    return values.W_Bool.make(a is values.w_false)

@expose("length", [values.W_List])
def length(a):
    n = 0
    while True:
        if isinstance(a, values.W_Null):
            return values.W_Fixnum(n)
        if isinstance(a, values.W_Cons):
            a = a.cdr()
            n = n+1
        else:
            raise SchemeException("length: not a list")

@expose("list")
def do_list(args):
    return values.to_list(args)

@expose("list*")
def do_liststar(args):
    if not args:
        raise SchemeException("list* expects at least one argument")
    return values.to_improper(args[:-1], args[-1])

@expose("assq", [values.W_Object, values.W_List])
def assq(a, b):
    while isinstance(b, values.W_Cons):
        head, b = b.car(), b.cdr()
        if not isinstance(head, values.W_Cons):
            raise SchemeException("assq: found a non-pair element")
        if eqp_logic(a, head.car()):
            return head
    if b is not values.w_null:
        raise SchemeException("assq: reached a non-pair")
    return values.w_false

@expose("cons", [values.W_Object, values.W_Object])
def do_cons(a, b):
    return values.W_Cons.make(a,b)

@expose("car", [values.W_Cons])
def do_car(a):
    return a.car()

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

@expose("cdr", [values.W_Cons])
def do_cdr(a):
    return a.cdr()


@expose("mlist")
def do_mlist(args):
    return values.to_mlist(args)

@expose("mcons", [values.W_Object, values.W_Object])
def do_mcons(a, b):
    return values.W_MCons(a,b)

@expose("mcar", [values.W_MCons])
def do_mcar(a):
    return a.car()

@expose("mcdr", [values.W_MCons])
def do_mcdr(a):
    return a.cdr()

@expose("set-mcar!", [values.W_MCons, values.W_Object])
def do_set_mcar(a, b):
    a.set_car(b)

@expose("set-mcdr!", [values.W_MCons, values.W_Object])
def do_set_mcdr(a, b):
    a.set_cdr(b)

@expose("for-each", [procedure, values.W_List], simple=False)
def for_each(f, l, env, cont):
    from pycket.interpreter import return_value
    return return_value(values.w_void, env, for_each_cont(f, l, env, cont))

@continuation
def for_each_cont(f, l, env, cont, vals):
    from pycket.interpreter import return_value
    if l is values.w_null:
        return return_value(values.w_void, env, cont)
    return f.call([l.car()], env, for_each_cont(f, l.cdr(), env, cont))

@expose("hash-for-each", [values.W_HashTable, procedure], simple=False)
def hash_for_each(h, f, env, cont):
    from pycket.interpreter import return_value
    return return_value(values.w_void, env, hash_for_each_cont(f,
                                                               h.data.keys(),
                                                               h.data, 0,
                                                               env, cont))

@continuation
def hash_for_each_cont(f, keys, data, n, env, cont, _vals):
    from pycket.interpreter import return_value
    if n == len(keys):
        return return_value(values.w_void, env, cont)
    return f.call([keys[n], data[keys[n]]], env,
                  hash_for_each_cont(f, keys, data, n+1, env, cont))

@expose("append")
def append(lists):
    if not lists:
        return values.w_null
    lists, acc = lists[:-1], lists[-1]
    while lists:
        vals = values.from_list(lists.pop())
        acc = values.to_improper(vals, acc)
    return acc

@expose("reverse", [values.W_List])
def reverse(w_l):
    acc = values.w_null
    while isinstance(w_l, values.W_Cons):
        val, w_l = w_l.car(), w_l.cdr()
        acc = values.W_Cons.make(val, acc)

    if w_l is not values.w_null:
        raise SchemeException("reverse: not given proper list")

    return acc

@expose("void")
def do_void(args): return values.w_void

@expose("make-inspector", [default(values_struct.W_StructInspector, None)])
def do_make_instpector(inspector):
    return values_struct.W_StructInspector.make(inspector)

@expose("make-sibling-inspector", [default(values_struct.W_StructInspector, None)])
def do_make_sibling_instpector(inspector):
    return values_struct.W_StructInspector.make(inspector, True)

@expose("current-inspector")
def do_current_instpector(args):
    return values_struct.current_inspector

@expose("struct?", [values.W_Object])
def do_is_struct(v):
    return values.W_Bool.make(isinstance(v, values_struct.W_RootStruct) and
                              not v.struct_type().isopaque)

@expose("struct-info", [values_struct.W_RootStruct])
def do_struct_info(struct):
    # TODO: if the current inspector does not control any
    # structure type for which the struct is an instance then return w_false
    struct_type = struct.struct_type() if True else values.w_false
    skipped = values.w_false
    return values.Values.make([struct_type, skipped])

@expose("struct-type-info", [values_struct.W_StructType])
def do_struct_type_info(struct_type):
    return values.Values.make(struct_type.struct_type_info())

@expose("struct-type-make-constructor", [values_struct.W_StructType])
def do_struct_type_make_constructor(struct_type):
    # TODO: if the type for struct-type is not controlled by the current inspector,
    # the exn:fail:contract exception should be raised
    return struct_type.constr

@expose("struct-type-make-predicate", [values_struct.W_StructType])
def do_struct_type_make_predicate(struct_type):
    # TODO: if the type for struct-type is not controlled by the current inspector,
    #the exn:fail:contract exception should be raised
    return struct_type.pred

@continuation
def attach_prop(struct_type, idx, prop, env, cont, _vals):
    from pycket.interpreter import check_one_val, jump
    struct_type.props[idx] = (prop, check_one_val(_vals))
    return jump(env, make_struct_type_cont(struct_type, idx + 1, env, cont))

@continuation
def make_struct_type_cont(struct_type, idx, env, cont, _vals):
    from pycket.interpreter import return_multi_vals
    if idx < len(struct_type.props):
        (prop, prop_val) = struct_type.props[idx]
        assert isinstance(prop, values_struct.W_StructProperty)
        if prop.guard.iscallable():
            return prop.guard.call([prop_val, values.to_list(struct_type.struct_type_info())],
                env, attach_prop(struct_type, idx, prop, env, cont))
    return return_multi_vals(values.Values.make(struct_type.make_struct_tuple()), env, cont)

@expose("make-struct-type",
        [values.W_Symbol, values.W_Object, values.W_Fixnum, values.W_Fixnum,
         default(values.W_Object, values.w_false),
         default(values.W_Object, values.w_null),
         default(values.W_Object, values.w_false),
         default(values.W_Object, values.w_false),
         default(values.W_Object, values.w_null),
         default(values.W_Object, values.w_false),
         default(values.W_Object, values.w_false)], simple=False)
def do_make_struct_type(name, super_type, init_field_cnt, auto_field_cnt,
        auto_v, props, inspector, proc_spec, immutables, guard, constr_name, env, cont):
    from pycket.interpreter import jump
    if not (isinstance(super_type, values_struct.W_StructType) or super_type is values.w_false):
        raise SchemeException("make-struct-type: expected a struct-type? or #f")
    struct_type = values_struct.W_StructType.make(name, super_type, init_field_cnt, auto_field_cnt,
            auto_v, props, inspector, proc_spec, immutables, guard, constr_name)
    return jump(env, make_struct_type_cont(struct_type, 0, env, cont))

@expose("make-struct-field-accessor",
        [values_struct.W_StructAccessor, values.W_Fixnum, default(values.W_Symbol, None)])
def do_make_struct_field_accessor(accessor, field, field_name):
    return values_struct.W_StructFieldAccessor(accessor, field, field_name)

@expose("make-struct-field-mutator",
        [values_struct.W_StructMutator, values.W_Fixnum, default(values.W_Symbol, None)])
def do_make_struct_field_mutator(mutator, field, field_name):
    return values_struct.W_StructFieldMutator(mutator, field, field_name)

@expose("struct->vector", [values_struct.W_RootStruct])
def expose_struct2vector(struct):
    return struct2vector(struct)

def struct2vector(struct):
    struct_desc = struct.struct_type().name
    first_el = values.W_Symbol.make("struct:" + struct_desc)
    return values_vector.W_Vector.fromelements([first_el] + struct.vals())

@expose("make-impersonator-property", [values.W_Symbol], simple=False)
def make_imp_prop(sym, env, cont):
    from pycket.interpreter import return_multi_vals
    from pycket.values import W_SimplePrim
    name = sym.value
    prop = imp.W_ImpPropertyDescriptor(name)
    pred = imp.W_ImpPropertyPredicate(name)
    accs = imp.W_ImpPropertyAccessor(name)
    return return_multi_vals(values.Values.make([prop, pred, accs]), env, cont)

@expose("make-struct-type-property", [values.W_Symbol,
                                      default(values.W_Object, values.w_false),
                                      default(values.W_List, values.w_null),
                                      default(values.W_Object, values.w_false)])
def mk_stp(sym, guard, supers, _can_imp):
    can_imp = False
    if guard is values.W_Symbol.make("can-impersonate"):
        guard = values.w_false
        can_imp = True
    if _can_imp is not values.w_false:
        can_imp = True
    prop = values_struct.W_StructProperty(sym, guard, supers, can_imp)
    return values.Values.make([prop,
                               values_struct.W_StructPropertyPredicate(prop),
                               values_struct.W_StructPropertyAccessor(prop)])

@expose("number->string", [values.W_Number])
def num2str(a):
    return values.W_String(a.tostring())

@expose("string->number", [values.W_String])
def str2num(w_s):
    from rpython.rlib import rarithmetic, rfloat, rbigint
    from rpython.rlib.rstring import ParseStringError, ParseStringOverflowError

    s = w_s.value
    try:
        if "." in s:
            return values.W_Flonum(rfloat.string_to_float(s))
        else:
            try:
                return values.W_Fixnum(rarithmetic.string_to_int(
                    s, base=0))
            except ParseStringOverflowError:
                return values.W_Bignum(rbigint.rbigint.fromstr(s))
    except ParseStringError as e:
        return values.w_false

### Boxes

@expose("box", [values.W_Object])
def box(v):
    return values.W_MBox(v)

@expose("box-immutable", [values.W_Object])
def box_immutable(v):
    return values.W_IBox(v)

@expose("unbox", [values.W_Box], simple=False)
def unbox(b, env, cont):
    return b.unbox(env, cont)

@expose("set-box!", [values.W_Box, values.W_Object], simple=False)
def set_box(box, v, env, cont):
    return box.set_box(v, env, cont)

# This implementation makes no guarantees about atomicity
@expose("box-cas!", [values.W_MBox, values.W_Object, values.W_Object])
def box_cas(box, old, new):
    if eqp_logic(box.value, old):
        box.value = new
        return values.w_true
    return values.w_false

@expose("make-weak-box", [values.W_Object])
def make_weak_box(val):
    return values.W_WeakBox(val)

@expose("weak-box-value", [values.W_WeakBox, default(values.W_Object, values.w_false)])
def weak_box_value(wb, default):
    v = wb.get()
    return v if v is not None else default

@expose("make-ephemeron", [values.W_Object] * 2)
def make_ephemeron(key, val):
    return values.W_Ephemeron(key, val)

@expose("ephemeron-value", [values.W_Ephemeron, default(values.W_Object, values.w_false)])
def ephemeron_value(ephemeron, default):
    v = ephemeron.get()
    return v if v is not None else default

@expose("make-placeholder", [values.W_Object])
def make_placeholder(val):
    return values.W_Placeholder(val)

@expose("placeholder-set!", [values.W_Placeholder, values.W_Object])
def placeholder_set(ph, datum):
    ph.value = datum
    return values.w_void

@expose("placeholder-get", [values.W_Placeholder])
def placeholder_get(ph):
    return ph.value

@expose("make-hash-placeholder", [values.W_List])
def make_hash_placeholder(vals):
    return values.W_HashTablePlaceholder([], [])

@expose("make-hasheq-placeholder", [values.W_List])
def make_hasheq_placeholder(vals):
    return values.W_HashTablePlaceholder([], [])

@expose("make-hasheqv-placeholder", [values.W_List])
def make_hasheqv_placeholder(vals):
    return values.W_HashTablePlaceholder([], [])

@expose("vector-ref", [values.W_MVector, values.W_Fixnum], simple=False)
def vector_ref(v, i, env, cont):
    idx = i.value
    if not (0 <= idx < v.length()):
        raise SchemeException("vector-ref: index out of bounds")
    return v.vector_ref(i, env, cont)

@expose("vector-set!", [values.W_MVector, values.W_Fixnum, values.W_Object], simple=False)
def vector_set(v, i, new, env, cont):
    idx = i.value
    if not (0 <= idx < v.length()):
        raise SchemeException("vector-set!: index out of bounds")
    return v.vector_set(i, new, env, cont)

@expose("vector-copy!",
        [values.W_MVector, values.W_Fixnum, values.W_MVector,
         default(values.W_Fixnum, None), default(values.W_Fixnum, None)], simple=False)
def vector_copy(dest, _dest_start, src, _src_start, _src_end, env, cont):
    src_start  = _src_start.value if _src_start is not None else 0
    src_end    = _src_end.value if _src_end is not None else src.length()
    dest_start = _dest_start.value

    src_range  = src_end - src_start
    dest_range = dest.length() - dest_start

    if not (0 <= dest_start < dest.length()):
        raise SchemeException("vector-copy!: destination start out of bounds")
    if not (0 <= src_start < src.length()) or not (0 <= src_start < src.length()):
        raise SchemeException("vector-copy!: source start/end out of bounds")
    if dest_range < src_range:
        raise SchemeException("vector-copy!: not enough room in target vector")

    return vector_copy_loop(src, src_start, src_end,
                dest, dest_start, values.W_Fixnum(0), env, cont)

@label
def vector_copy_loop(src, src_start, src_end, dest, dest_start, i, env, cont):
    from pycket.interpreter import return_value
    src_idx = i.value + src_start
    if src_idx >= src_end:
        return return_value(values.w_void, env, cont)
    idx = values.W_Fixnum(src_idx)
    return src.vector_ref(idx, env,
                vector_copy_cont_get(src, src_start, src_end, dest,
                    dest_start, i, env, cont))

@continuation
def goto_vector_copy_loop(src, src_start, src_end, dest, dest_start, next, env, cont, _vals):
    return vector_copy_loop(
            src, src_start, src_end, dest, dest_start, next, env, cont)

@continuation
def vector_copy_cont_get(src, src_start, src_end, dest, dest_start, i, env, cont, _vals):
    from pycket.interpreter import check_one_val
    val  = check_one_val(_vals)
    idx  = values.W_Fixnum(i.value + dest_start)
    next = values.W_Fixnum(i.value + 1)
    return dest.vector_set(idx, val, env,
                goto_vector_copy_loop(src, src_start, src_end,
                    dest, dest_start, next, env, cont))

def find_prop_start_index(args):
    for i, v in enumerate(args):
        if isinstance(v, imp.W_ImpPropertyDescriptor):
            return i
    return len(args)

def unpack_properties(args, name):
    idx = find_prop_start_index(args)
    args, props = args[:idx], args[idx:]
    prop_len = len(props)

    if prop_len % 2 != 0:
        raise SchemeException(name + ": not all properties have corresponding values")

    prop_keys = [props[i] for i in range(0, prop_len, 2)]
    prop_vals = [props[i] for i in range(1, prop_len, 2)]

    for k in prop_keys:
        if not isinstance(k, imp.W_ImpPropertyDescriptor):
            desc = name + ": %s is not a property descriptor" % k.tostring()
            raise SchemeException(desc)

    return args, prop_keys, prop_vals

def unpack_vector_args(args, name):
    args, prop_keys, prop_vals = unpack_properties(args, name)
    if len(args) != 3:
        raise SchemeException(name + ": not given 3 required arguments")
    v, refh, seth = args
    if not isinstance(v, values.W_MVector):
        raise SchemeException(name + ": first arg not a vector")
    if not refh.iscallable() or not seth.iscallable:
        raise SchemeException(name + ": provided handler is not callable")

    return v, refh, seth, prop_keys, prop_vals

def unpack_procedure_args(args, name):
    args, prop_keys, prop_vals = unpack_properties(args, name)
    if len(args) != 2:
        raise SchemeException(name + ": not given 2 required arguments")
    proc, check = args
    if not proc.iscallable():
        raise SchemeException(name + ": first argument is not a procedure")
    if not check.iscallable():
        raise SchemeException(name + ": handler is not a procedure")
    return proc, check, prop_keys, prop_vals

def unpack_box_args(args, name):
    args, prop_keys, prop_vals = unpack_properties(args, name)
    if len(args) != 3:
        raise SchemeException(name + ": not given three required arguments")
    box, unboxh, seth = args
    if not unboxh.iscallable():
        raise SchemeException(name + ": supplied unbox handler is not callable")
    if not seth.iscallable():
        raise SchemeException(name + ": supplied set-box! handler is not callable")
    return box, unboxh, seth, prop_keys, prop_vals

@expose("impersonate-procedure")
def impersonate_procedure(args):
    proc, check, prop_keys, prop_vals = unpack_procedure_args(args, "impersonate-procedure")
    check.mark_non_loop()
    return imp.W_ImpProcedure(proc, check, prop_keys, prop_vals)

@expose("impersonate-vector")
def impersonate_vector(args):
    v, refh, seth, prop_keys, prop_vals = unpack_vector_args(args, "impersonate-vector")
    if v.immutable():
        raise SchemeException("Cannot impersonate immutable vector")
    refh.mark_non_loop()
    seth.mark_non_loop()
    return imp.W_ImpVector(v, refh, seth, prop_keys, prop_vals)

@expose("chaperone-procedure")
def chaperone_procedure(args):
    proc, check, prop_keys, prop_vals = unpack_procedure_args(args, "chaperone-procedure")
    check.mark_non_loop()
    return imp.W_ChpProcedure(proc, check, prop_keys, prop_vals)

@expose("chaperone-vector")
def chaperone_vector(args):
    v, refh, seth, prop_keys, prop_vals = unpack_vector_args(args, "chaperone-vector")
    refh.mark_non_loop()
    seth.mark_non_loop()
    return imp.W_ChpVector(v, refh, seth, prop_keys, prop_vals)

# Need to check that fields are mutable
@expose("impersonate-struct")
def impersonate_struct(args):
    args, prop_keys, prop_vals = unpack_properties(args, "impersonate-struct")
    if len(args) < 1 or len(args) % 2 != 1:
        raise SchemeException("impersonate-struct: arity mismatch")
    if len(args) == 1:
        return args[0]

    struct, args = args[0], args[1:]

    if not isinstance(struct, values_struct.W_Struct):
        raise SchemeException("impersonate-struct: not given struct")

    struct_type = struct.struct_type()
    assert isinstance(struct_type, values_struct.W_StructType)

    # Consider storing immutables in an easier form in the structs implementation
    immutables = struct_type.immutables

    # Slicing would be nicer
    overrides = [args[i] for i in range(0, len(args), 2)]
    handlers  = [args[i] for i in range(1, len(args), 2)]

    for i in overrides:
        if not imp.valid_struct_proc(i):
            raise SchemeException("impersonate-struct: not given valid field accessor")
        elif (isinstance(i, values_struct.W_StructFieldMutator) and
                i.field.value in immutables):
            raise SchemeException("impersonate-struct: cannot impersonate immutable field")
        elif (isinstance(i, values_struct.W_StructFieldAccessor) and
                i.field.value in immutables):
            raise SchemeException("impersonate-struct: cannot impersonate immutable field")

    for i in handlers:
        if not i.iscallable():
            raise SchemeException("impersonate-struct: supplied hander is not a procedure")

    return imp.W_ImpStruct(struct, overrides, handlers, prop_keys, prop_vals)

@expose("chaperone-struct")
def chaperone_struct(args):
    args, prop_keys, prop_vals = unpack_properties(args, "chaperone-struct")
    if len(args) < 1 or len(args) % 2 != 1:
        raise SchemeException("chaperone-struct: arity mismatch")
    if len(args) == 1:
        return args[0]

    struct, args = args[0], args[1:]

    if not isinstance(struct, values_struct.W_Struct):
        raise SchemeException("chaperone-struct: not given struct")

    # Slicing would be nicer
    overrides = [args[i] for i in range(0, len(args), 2)]
    handlers  = [args[i] for i in range(1, len(args), 2)]

    for i in overrides:
        if not imp.valid_struct_proc(i):
            raise SchemeException("chaperone-struct: not given valid field accessor")

    for i in handlers:
        if not i.iscallable():
            raise SchemeException("chaperone-struct: supplied hander is not a procedure")

    return imp.W_ChpStruct(struct, overrides, handlers, prop_keys, prop_vals)

@expose("chaperone-box")
def chaperone_box(args):
    b, unbox, set, prop_keys, prop_vals = unpack_box_args(args, "chaperone-box")
    unbox.mark_non_loop()
    set.mark_non_loop()
    return imp.W_ChpBox(b, unbox, set, prop_keys, prop_vals)

@expose("impersonate-box")
def impersonate_box(args):
    b, unbox, set, prop_keys, prop_vals = unpack_box_args(args, "impersonate-box")
    if b.immutable():
        raise SchemeException("Cannot impersonate immutable box")
    unbox.mark_non_loop()
    set.mark_non_loop()
    return imp.W_ImpBox(b, unbox, set, prop_keys, prop_vals)

@expose("chaperone-continuation-mark-key", [values.W_ContinuationMarkKey, values.W_Object])
def ccmk(cmk, f):
    return cmk

@expose("impersonate-continuation-mark-key", [values.W_ContinuationMarkKey, values.W_Object])
def icmk(cmk, f):
    return cmk

@expose("chaperone-of?", [values.W_Object, values.W_Object])
def chaperone_of(a, b):
    return values.W_Bool.make(imp.is_chaperone_of(a, b))

@expose("impersonator-of?", [values.W_Object, values.W_Object])
def impersonator_of(a, b):
    return values.W_Bool.make(imp.is_impersonator_of(a, b))

@expose("impersonator?", [values.W_Object])
def impersonator(x):
    return values.W_Bool.make(x.is_impersonator())

@expose("chaperone?", [values.W_Object])
def chaperone(x):
    return values.W_Bool.make(x.is_chaperone())

@expose("vector")
def vector(args):
    return values_vector.W_Vector.fromelements(args)

@expose("make-vector", [values.W_Fixnum, default(values.W_Object, values.W_Fixnum(0))])
def make_vector(w_size, w_val):
    size = w_size.value
    if not size >= 0:
        raise SchemeException("make-vector: expected a positive fixnum")
    return values_vector.W_Vector.fromelement(w_val, size)

@expose("vector-length", [values_vector.W_MVector])
def vector_length(v):
    return values.W_Fixnum(v.length())

# my kingdom for a tail call
def listp_loop(v):
    while True:
        if v is values.w_null: return True
        if isinstance(v, values.W_Cons):
            v = v.cdr()
            continue
        return False

@expose("list?", [values.W_Object])
def consp(v):
    return values.W_Bool.make(listp_loop(v))

@expose("current-inexact-milliseconds", [])
def curr_millis():
    return values.W_Flonum(time.clock()*1000)

@expose("error", [values.W_Symbol, values.W_String])
def error(name, msg):
    raise SchemeException("%s: %s"%(name.tostring(), msg.tostring()))

@expose("list->vector", [values.W_List])
def list2vector(l):
    return values_vector.W_Vector.fromelements(values.from_list(l))

# FIXME: make this work with chaperones/impersonators
@expose("vector->list", [values_vector.W_Vector])
def vector2list(v):
    es = []
    for i in range(v.length()):
        es.append(v.ref(i))
    return values.to_list(es)

@expose("vector->immutable-vector", [values_vector.W_Vector])
def vector2immutablevector(v):
    # FIXME: it should be immutable
    return v

# FIXME: make that a parameter
@expose("current-command-line-arguments", [], simple=False)
def current_command_line_arguments(env, cont):
    from pycket.interpreter import return_value
    w_v = values_vector.W_Vector.fromelements(
            env.toplevel_env.commandline_arguments)
    return return_value(w_v, env, cont)

# ____________________________________________________________

## Unsafe Fixnum ops
@expose("unsafe-fx+", [unsafe(values.W_Fixnum)] * 2)
def unsafe_fxplus(a, b):
    return values.W_Fixnum(a.value + b.value)

@expose("unsafe-fx-", [unsafe(values.W_Fixnum)] * 2)
def unsafe_fxminus(a, b):
    return values.W_Fixnum(a.value - b.value)

@expose("unsafe-fx*", [unsafe(values.W_Fixnum)] * 2)
def unsafe_fxtimes(a, b):
    return values.W_Fixnum(a.value * b.value)

@expose("unsafe-fx<", [unsafe(values.W_Fixnum)] * 2)
def unsafe_fxlt(a, b):
    return values.W_Bool.make(a.value < b.value)

@expose("unsafe-fx>", [unsafe(values.W_Fixnum)] * 2)
def unsafe_fxgt(a, b):
    return values.W_Bool.make(a.value > b.value)

@expose("unsafe-fx=", [unsafe(values.W_Fixnum)] * 2)
def unsafe_fxeq(a, b):
    return values.W_Bool.make(a.value == b.value)

@expose("unsafe-fx->fl", [unsafe(values.W_Fixnum)])
def unsafe_fxfl(a):
    return values.W_Flonum(float(a.value))

## Unsafe Flonum ops
@expose("unsafe-fl+", [unsafe(values.W_Flonum)] * 2)
def unsafe_flplus(a, b):
    return values.W_Flonum(a.value + b.value)

@expose("unsafe-fl-", [unsafe(values.W_Flonum)] * 2)
def unsafe_flminus(a, b):
    return values.W_Flonum(a.value - b.value)

@expose("unsafe-fl*", [unsafe(values.W_Flonum)] * 2)
def unsafe_fltimes(a, b):
    return values.W_Flonum(a.value * b.value)

@expose("unsafe-fl/", [unsafe(values.W_Flonum)] * 2)
def unsafe_fldiv(a, b):
    return values.W_Flonum(a.value / b.value)

@expose("unsafe-fl<", [unsafe(values.W_Flonum)] * 2)
def unsafe_fllt(a, b):
    return values.W_Bool.make(a.value < b.value)

@expose("unsafe-fl<=", [unsafe(values.W_Flonum)] * 2)
def unsafe_fllte(a, b):
    return values.W_Bool.make(a.value <= b.value)

@expose("unsafe-fl>", [unsafe(values.W_Flonum)] * 2)
def unsafe_flgt(a, b):
    return values.W_Bool.make(a.value > b.value)

@expose("unsafe-fl>=", [unsafe(values.W_Flonum)] * 2)
def unsafe_flgte(a, b):
    return values.W_Bool.make(a.value >= b.value)

@expose("unsafe-fl=", [unsafe(values.W_Flonum)] * 2)
def unsafe_fleq(a, b):
    return values.W_Bool.make(a.value == b.value)

## Unsafe vector ops

# FIXME: Chaperones
@expose("unsafe-vector-ref", [values.W_Object, unsafe(values.W_Fixnum)], simple=False)
def unsafe_vector_ref(v, i, env, cont):
    from pycket.interpreter import return_value
    if isinstance(v, imp.W_ImpVector) or isinstance(v, imp.W_ChpVector):
        return v.vector_ref(i, env, cont)
    else:
        assert type(v) is values_vector.W_Vector
        val = i.value
        assert val >= 0
        return return_value(v._ref(val), env, cont)

@expose("unsafe-vector*-ref", [unsafe(values_vector.W_Vector), unsafe(values.W_Fixnum)])
def unsafe_vector_star_ref(v, i):
    return v._ref(i.value)

# FIXME: Chaperones
@expose("unsafe-vector-set!", [values.W_Object, unsafe(values.W_Fixnum), values.W_Object], simple=False)
def unsafe_vector_set(v, i, new, env, cont):
    from pycket.interpreter import return_value
    if isinstance(v, imp.W_ImpVector) or isinstance(v, imp.W_ChpVector):
        return v.vector_set(i, new, env, cont)
    else:
        assert type(v) is values_vector.W_Vector
        return return_value(v._set(i.value, new), env, cont)

@expose("unsafe-vector*-set!",
        [unsafe(values_vector.W_Vector), unsafe(values.W_Fixnum), values.W_Object])
def unsafe_vector_star_set(v, i, new):
    return v._set(i.value, new)

@expose("unsafe-vector-length", [values.W_MVector])
def unsafe_vector_length(v):
    return values.W_Fixnum(v.length())

@expose("unsafe-vector*-length", [unsafe(values_vector.W_Vector)])
def unsafe_vector_star_length(v):
    return values.W_Fixnum(v.length())

# Unsafe struct ops
@expose("unsafe-struct-ref", [values.W_Object, unsafe(values.W_Fixnum)])
def unsafe_struct_ref(v, k):
    while isinstance(v, imp.W_ChpStruct) or isinstance(v, imp.W_ImpStruct):
        v = v.inner
    assert isinstance(v, values_struct.W_Struct)
    assert 0 <= k.value <= v.struct_type().total_field_cnt
    return v._ref(k.value)

@expose("unsafe-struct-set!", [values.W_Object, unsafe(values.W_Fixnum), values.W_Object])
def unsafe_struct_set(v, k, val):
    while isinstance(v, imp.W_ChpStruct) or isinstance(v, imp.W_ImpStruct):
        v = v.inner
    assert isinstance(v, values_struct.W_Struct)
    assert 0 <= k.value < v.struct_type().total_field_cnt
    return v._set(k.value, val)

@expose("unsafe-struct*-ref", [values_struct.W_Struct, unsafe(values.W_Fixnum)])
def unsafe_struct_star_ref(v, k):
    assert 0 <= k.value < v.struct_type().total_field_cnt
    return v._ref(k.value)

@expose("unsafe-struct*-set!", [values_struct.W_Struct, unsafe(values.W_Fixnum), values.W_Object])
def unsafe_struct_star_set(v, k, val):
    assert 0 <= k.value <= v.struct_type().total_field_cnt
    return v._set(k.value, val)

# Unsafe pair ops
@expose("unsafe-car", [values.W_Cons])
def unsafe_car(p):
    return p.car()

@expose("unsafe-cdr", [values.W_Cons])
def unsafe_cdr(p):
    return p.cdr()

@expose("hash")
def hash(args):
    return values.W_HashTable([], [])

@expose("hasheq")
def hasheq(args):
    return values.W_HashTable([], [])

@expose("make-hash")
def make_hash(args):
    return values.W_HashTable([], [])

@expose("make-hasheq")
def make_hasheq(args):
    return values.W_HashTable([], [])

@expose("hash-set!", [values.W_HashTable, values.W_Object, values.W_Object])
def hash_set_bang(ht, k, v):
    ht.set(k, v)
    return values.w_void

@expose("hash-ref", [values.W_HashTable, values.W_Object, default(values.W_Object, None)], simple=False)
def hash_set_bang(ht, k, default, env, cont):
    from pycket.interpreter import return_value
    val = ht.ref(k)
    if val:
        return return_value(val, env, cont)
    elif isinstance(default, procedure):
        return val.call([], env, cont)
    elif default:
        return return_value(default, env, cont)
    else:
        raise SchemeException("key not found")

@expose("path->bytes", [values.W_Path])
def path2bytes(p):
    return values.W_Bytes(p.path)


@expose("symbol->string", [values.W_Symbol])
def symbol_to_string(v):
    return values.W_String(v.value)

@expose("string->symbol", [values.W_String])
def string_to_symbol(v):
    return values.W_Symbol.make(v.value)

@expose("string->unreadable-symbol", [values.W_String])
def string_to_unsymbol(v):
    return values.W_Symbol.make_unreadable(v.value)

@expose("symbol-unreadable?", [values.W_Symbol])
def sym_unreadable(v):
    if v.unreadable:
        return values.w_true
    return values.w_false

@expose("symbol-interned?", [values.W_Symbol])
def string_to_symbol(v):
    return values.W_Bool.make(v.is_interned())

@expose("string->uninterned-symbol", [values.W_String])
def string_to_symbol(v):
    return values.W_Symbol(v.value)

@expose("string->bytes/locale", [values.W_String,
                                 default(values.W_Object, values.w_false),
                                 default(values.W_Integer, values.W_Fixnum(0)),
                                 default(values.W_Integer, None)])
def string_to_bytes_locale(str, errbyte, start, end):
    # FIXME: This ignores the locale
    return values.W_Bytes(str.value)

@expose("integer->char", [values.W_Fixnum])
def integer_to_char(v):
    return values.W_Character(unichr(v.value))

@expose("immutable?", [values.W_Object])
def immutable(v):
    return values.W_Bool.make(v.immutable())

@expose("eval-jit-enabled", [])
def jit_enabled():
    return values.w_true

@expose("make-thread-cell", [values.W_Object, default(values.W_Bool, values.w_false)])
def make_thread_cell(v, pres):
    return values.W_ThreadCell(v, pres)

@expose("thread-cell-ref", [values.W_ThreadCell])
def thread_cell_ref(cell):
    return cell.value

@expose("thread-cell-set!", [values.W_ThreadCell, values.W_Object])
def thread_cell_set(cell, v):
    cell.value = v
    return values.w_void

@expose("current-preserved-thread-cell-values", [default(values.W_ThreadCellValues, None)])
def current_preserved_thread_cell_values(v):
    # Generate a new thread-cell-values object
    if v is None:
        return values.W_ThreadCellValues()

    # Otherwise, we restore the values
    for cell, val in v.assoc.items():
        assert cell.preserved.value
        cell.value = val
    return values.w_void

@expose("current-continuation-marks", [], simple=False)
def current_cont_marks(env, cont):
    from pycket.interpreter import return_value
    return return_value(values.W_ContinuationMarkSet(cont), env, cont)

@expose("continuation-mark-set->list", [values.W_ContinuationMarkSet, values.W_Object])
def cms_list(cms, mark):
    return cont.get_marks(cms.cont, mark)

@expose("continuation-mark-set-first", [values.W_Object, values.W_Object, default(values.W_Object, values.w_false)], simple=False)
def cms_list(cms, mark, missing, env, con):
    from pycket.interpreter import return_value
    if cms is values.w_false:
        the_cont = con
    elif isinstance(cms, values.W_ContinuationMarkSet):
        the_cont = cms.cont
    else:
        raise SchemeException("Expected #f or a continuation-mark-set")
    v = cont.get_mark_first(the_cont, mark)
    if v:
        return return_value(v, env, con)
    else:
        return return_value(missing, env, con)

@expose("extend-parameterization", [values.W_Object, values.W_Object, values.W_Object])
def extend_paramz(paramz, key, val):
    if isinstance(paramz, values.W_Parameterization):
        return paramz.extend(key, val)
    else:
        return paramz # This really is the Racket behavior

@expose("make-continuation-mark-key", [values.W_Symbol])
def mk_cmk(s):
    return values.W_ContinuationMarkKey(s)

@expose("make-continuation-prompt-tag", [])
def mcpt():
    return values.W_ContinuationPromptTag()

@expose("gensym", [default(values.W_Symbol, values.W_Symbol.make("g"))])
def gensym(init):
    from pycket.interpreter import Gensym
    return Gensym.gensym(init.value)

@expose("regexp-match", [values.W_AnyRegexp, values.W_Object]) # FIXME: more error checking
def regexp_match(r, o):
    return values.w_false # Back to one problem

@expose("regexp-match?", [values.W_AnyRegexp, values.W_Object]) # FIXME: more error checking
def regexp_matchp(r, o):
    # ack, this is wrong
    return values.w_true # Back to one problem

@expose("build-path")
def build_path(args):
    # this is terrible
    r = ""
    for a in args:
        if isinstance(a, values.W_Bytes):
            r = r + a.value
        elif isinstance(a, values.W_String):
            r = r + a.value
        elif isinstance(a, values.W_Path):
            r = r + a.path
        else:
            raise SchemeException("bad input to build-path: %s"%a)
    return values.W_Path(r)

@expose("current-environment-variables", [])
def cur_env_vars():
    return values.W_EnvVarSet()

@expose("environment-variables-ref", [values.W_EnvVarSet, values.W_Bytes])
def env_var_ref(set, name):
    return values.w_false

@expose("raise-argument-error", [values.W_Symbol, values.W_String, values.W_Object])
def raise_arg_err(sym, str, val):
    raise SchemeException("%s: expected %s but got %s"%(sym.value, str.value, val.tostring()))

@expose("find-system-path", [values.W_Symbol])
def find_sys_path(sym):
    from pycket import interpreter
    v = interpreter.GlobalConfig.lookup(sym.value)
    if v:
        return values.W_Path(v)
    else:
        raise SchemeException("unknown system path %s"%sym.value)

@expose("system-type", [default(values.W_Symbol, values.W_Symbol.make("os"))])
def system_type(sym):
    if sym is values.W_Symbol.make("os"):
        # FIXME: make this work on macs
        return values.W_Symbol.make("unix")
    raise SchemeException("unexpected system-type symbol %s"%sym.value)

@expose("find-main-collects", [])
def find_main_collects():
    return values.w_false

@expose("module-path-index-join", [values.W_Object, values.W_Object])
def mpi_join(a, b):
    return values.W_ModulePathIndex()

# Loading

# FIXME: Proper semantics.
@expose("load", [values.W_String], simple=False)
def load(lib, env, cont):
    from pycket.expand import ensure_json_ast_load, load_json_ast_rpython
    lib_name = lib.tostring()
    json_ast = ensure_json_ast_load(lib_name)
    if json_ast is None:
        raise SchemeException(
            "can't gernerate load-file for %s "%(lib.tostring()))
    ast = load_json_ast_rpython(json_ast)
    return ast, env, cont

# FIXME : Make the random functions actually do what they are supposed to do
# random things
@expose("random")
def random(args):
    return values.W_Fixnum(1)

@expose("random-seed", [values.W_Fixnum])
def random_seed(seed):
    return values.w_void

@expose("make-pseudo-random-generator", [])
def make_pseudo_random_generator():
    return values.W_PseudoRandomGenerator()

@expose("current-pseudo-random-generator")
def current_pseudo_random_generator(args):
    if not args:
        return values.W_PseudoRandomGenerator()
    return values.w_void

@expose("pseudo-random-generator->vector", [values.W_PseudoRandomGenerator])
def pseudo_random_generator_to_vector(gen):
    return values_vector.W_Vector.fromelements([])

@expose("vector->pseudo-random-generator", [values.W_PseudoRandomGenerator, default(values.W_MVector, None)])
def vector_to_pseudo_random_generator(gen, vec):
    return values.W_PseudoRandomGenerator()

@expose("pseudo-random-generator-vector?", [values.W_Object])
def pseudo_random_generator_vector_huh(vec):
    return values.W_Bool.make(isinstance(vec, values.W_MVector) and vec.length() == 0)
