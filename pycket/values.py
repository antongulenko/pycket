from pycket.error import SchemeException
from rpython.tool.pairtype import extendabletype
from rpython.rlib  import jit

class W_Object(object):
    __metaclass__ = extendabletype
    _attrs_ = []
    errorname = "%%%%unreachable%%%%"
    def __init__(self):
        raise NotImplementedError("abstract base class")
    def tostring(self):
        return str(self)
    def call(self, args, env, frame):
        raise SchemeException("%s is not callable" % self.tostring())

class W_Cell(W_Object): # not the same as Racket's box
    def __init__(self, v):
        assert not isinstance(v, W_Cell)
        self.value = v

class W_Number(W_Object):
    errorname = "number"
    def __init__(self):
        raise NotImplementedError("abstract base class")

class W_Fixnum(W_Number):
    _immutable_fields_ = ["value"]
    errorname = "fixnum"
    def tostring(self):
        return str(self.value)
    def __init__(self, val):
        self.value = val

class W_Flonum(W_Number):
    _immutable_fields_ = ["value"]
    def tostring(self):
        return str(self.value)
    def __init__(self, val):
        self.value = val

class W_Bignum(W_Number):
    _immutable_fields_ = ["value"]
    def tostring(self):
        return str(self.value)
    def __init__(self, val):
        self.value = val

class W_Void(W_Object):
    def __init__(self): pass
    def tostring(self):
        return "#<void>"

w_void = W_Void()

class W_Bool(W_Object):
    _immutable_fields_ = ["value"]
    @staticmethod
    def make(b):
        if b: return w_true
        else: return w_false
    def __init__(self, val):
        self.value = val
    def tostring(self):
        if self.value: return "#t"
        else: return "#f"

w_false = W_Bool(False)
w_true = W_Bool(True)

class W_String(W_Object):
    def __init__(self, val):
        self.value = val
    def tostring(self):
        return self.value

class W_Symbol(W_Object):
    _immutable_fields_ = ["value"]
    all_symbols = {}
    @staticmethod
    def make(string):
        # This assert statement makes the lowering phase of rpython break...
        # Maybe comment back in and check for bug.
        #assert isinstance(string, str)
        if string in W_Symbol.all_symbols:
            return W_Symbol.all_symbols[string]
        else:
            W_Symbol.all_symbols[string] = w_result = W_Symbol(string)
            return w_result
    def __repr__(self):
        return self.value
    def __init__(self, val):
        self.value = val
    def tostring(self):
        return "'%s"%self.value
