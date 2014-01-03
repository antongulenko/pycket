
from pycket.values import W_Object, W_Fixnum

class W_List(W_Object):
    errorname = "list"
    def __init__(self):
        raise NotImplementedError("abstract base class")

class W_AbstractCons(W_List):
    errorname = "pair"
    def __init__(self, a, d):
        self.set_car(a)
        self.set_cdr(d)
    def get_car(self):
        raise NotImplementedError("abstract base class")
    def get_cdr(self):
        raise NotImplementedError("abstract base class")
    def set_car(self, car):
        raise NotImplementedError("abstract base class")
    def set_cdr(self, cdr):
        raise NotImplementedError("abstract base class")

class W_Cons(W_AbstractCons):
    "The regular cons-cell pointing to two wrapped values (instances of W_Object)."
    errorname = "pair"
    def get_car(self):
        return self.car
    def get_cdr(self):
        return self.cdr
    def set_car(self, car):
        self.car = car
    def set_cdr(self, cdr):
        self.cdr = cdr
    def tostring(self):
        # TODO fix printing of cons-cells: '(1 2) instead of '(1 . (2 . ()))
        return "(%s . %s)" % (self.get_car().tostring(), self.get_cdr().tostring())

class W_FixnumCons(W_AbstractCons):
    "This cons-cell contains an unwrapped Fixnum (int)."
    "The car-field of this cons-cell is type-immutable."
    errorname = "pair"
    def get_car(self):
        return W_Fixnum(self.car)
    def get_cdr(self):
        return self.cdr
    def set_car(self, car):
        assert isinstance(a, W_Fixnum)
        self.car = a.value
    def set_cdr(self, cdr):
        self.cdr = cdr

class W_FixnumArrayCons(W_AbstractCons):
    "This cons-cell is optimized for a list of Fixnums with a fixed size."
    "It contains a pointer to W_FixnumArray and an offset."
    errorname = "pair"
    def __init__(self, arr, offset):
        self.arr = arr
        self.offset = offset
    def get_car(self):
        return W_Fixnum(self.arr.at(self.offset))
    def get_cdr(self):
        if self.arr.length() <= self.offset:
            return w_null
        return W_FixnumArrayCons(self.arr, self.offset + 1)
    def set_car(self, car):
        assert isinstance(a, W_Fixnum)
        self.arr.put(offset, car.value)
    def set_cdr(self, cdr):
        # TODO -- deoptimize
        raise SchemeException("Cannot mutate cdr of an optimized cons.")

class W_FixnumArray(W_Object):
    "We use an indirection through an instance of this class instead of directly referencing an rpython-list."
    "Purpose: make the list resizable/reallocatable, making it possible to append to the list."
    def __init__(self, arr):
        self.arr = arr
    def length(self):
        return len(self.arr)
    def at(self, i):
        return self.arr[i]
    def put(self, i, val):
        self.arr[i] = val

class W_Null(W_List):
    def __init__(self): pass
    def tostring(self): return "'()"

w_null = W_Null()

def to_list(l): return to_improper(l, w_null)

def to_improper(l, v):
    if not l:
        return v
    else:
        return W_Cons(l[0], to_improper(l[1:], v))
