
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
    def get_car(self):
        return self.car
    def get_cdr(self):
        return self.cdr
    def set_car(self, car):
        self.car = car
    def set_cdr(self, cdr):
        self.cdr = cdr
    def tostring(self):
        return "(%s . %s)"%(self.car.tostring(), self.cdr.tostring())

class W_FixnumCons(W_AbstractCons):
    "This cons-cell contains an unwrapped Fixnum (int)."
    def get_car(self):
        return W_Fixnum(self.car)
    def get_cdr(self):
        return self.cdr
    def set_car(self, car):
        assert isinstance(a, W_Fixnum)
        self.car = a.value
    def set_cdr(self, cdr):
        self.cdr = cdr
    def tostring(self):
        return "(%s . %s)"%(str(self.car), self.cdr.tostring())        

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
