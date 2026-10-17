import os
state = {}
count = 0

def mutate(key):
    state[key] = 1
    global count, created
    count = 3
    created = 4
    local = {}
    local[key] = 5

def parameter(state, key):
    state[key] = 1

def rebound(key):
    state = {}
    state[key] = 1

def nested(key):
    def shadow(state):
        state[key] = 2
    state[key] = 3

class Owner:
    state = {}
    def update(self, key):
        state[key] = 4
        self.field = 1
        os.environ['REVEAL_TEST_STATE'] = '1'

def enclosing():
    cell = {}
    def closure(key):
        nonlocal cell
        cell[key] = 2
        cell = {}
    return closure

class BuiltinOwner:
    print = lambda value: value
    def builtin_method(self):
        print('still builtin')

def capture_owner():
    captured = {}
    def implicit_capture(key):
        captured[key] = 1
    return implicit_capture
