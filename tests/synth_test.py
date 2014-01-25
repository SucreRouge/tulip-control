# WARNING: This example may not yet be working.  Please check again in
#          the upcoming release.
#
# This is an example to demonstrate how the output of abstracting a switched
# system, where the only control over the dynamics is through mode switching
# might look like.

# NO, 6 Jan 2014.

# We will assume, we have the 6 cell robot example.

#
#     +---+---+
#     | 2 | 3 |
#     +---+---+
#     | 0 | 1 | 
#     +---+---+
#

import logging
logging.basicConfig(level=logging.DEBUG)

from tulip import spec, synth, transys
import numpy as np
from scipy import sparse as sp

###############################
# Switched system with 2 modes:
###############################

# In this scenario we have limited actions "left, right" with 
# uncertain (nondeterministics) outcomes (e.g., due to bad actuators or 
# bad low-level feedback controllers)

# Only control over the dynamics is through mode switching
# Transitions should be interpreted as nondeterministic

# Create a finite transition system
env_sws = transys.OpenFTS()

env_sws.sys_actions.add_from({'right','left'})

# str states
n = 4
states = transys.prepend_with(range(n), 's')
env_sws.states.add_from(set(states) )

# mode1 transitions
transmat1 = np.array([[0,1,0,1],
                      [0,1,0,0],
                      [0,1,0,1],
                      [0,0,0,1]])
env_sws.transitions.add_labeled_adj(
    sp.lil_matrix(transmat1), states, {'sys_actions':'right'}
)
                      
# mode2 transitions
transmat2 = np.array([[1,0,0,0],
                      [1,0,1,0],
                      [0,0,1,0],
                      [1,0,1,0]])
env_sws.transitions.add_labeled_adj(
    sp.lil_matrix(transmat2), states, {'sys_actions':'left'}
)


# Decorate TS with state labels (aka atomic propositions)
env_sws.atomic_propositions.add_from(['home','lot'])
env_sws.states.labels(
    states, [set(),set(),{'home'},{'lot'}]
)

# This is what is visible to the outside world (and will go into synthesis method)
print(env_sws)

#
# Environment variables and specification
#
# The environment can issue a park signal that the robot just respond
# to by moving to the left of the grid.  We assume that
# the park signal is turned off infinitely often.
#
env_vars = {'park'}
env_init = {'eloc = 0', 'park'}
env_prog = {'!park'}
env_safe = set()                # empty set

# 
# System specification
#
# The system specification is that the robot should repeatedly revisit
# the right side of the grid while at the same time responding
# to the park signal by visiting the left side.  The LTL
# specification is given by 
#
#     []<> home && [](park -> <>lot)
#
# Since this specification is not in GR(1) form, we introduce the
# variable X0reach that is initialized to True and the specification
# [](park -> <>lot) becomes
#
#     [](next(X0reach) <-> lot || (X0reach && !park))
#

# Augment the environmental description to make it GR(1)
#! TODO: create a function to convert this type of spec automatically

# Define the specification
#! NOTE: maybe "synthesize" should infer the atomic proposition from the 
# transition system? Or, we can declare the mode variable, and the values
# of the mode variable are read from the transition system.
sys_vars = {'X0reach'}
sys_init = {'X0reach'}          
sys_prog = {'home'}               # []<>home
sys_safe = {'next(X0reach) <-> lot || (X0reach && !park)'}
sys_prog |= {'X0reach'}

# Create the specification
specs = spec.GRSpec(env_vars, sys_vars, env_init, sys_init,
                    env_safe, sys_safe, env_prog, sys_prog)
                    
# Controller synthesis
#
# At this point we can synthesize the controller using one of the available
# methods.  Here we make use of JTLV.
#
r = synth.is_realizable('gr1c', specs, env=env_sws, ignore_env_init=True)
assert(not r)

def sys_fts_2_states():
    sys = transys.FTS()
    sys.states.add_from(['X0', 'X1'])
    sys.states.initial.add_from(['X0', 'X1'])
    
    sys.transitions.add_from({'X0'}, {'X1'})
    sys.transitions.add_from({'X1'}, {'X0', 'X1'})
    
    sys.atomic_propositions.add_from({'home', 'lot'})
    sys.states.label('X0', 'home')
    sys.states.label('X1', 'lot')
    
    #sys.plot()
    return sys

def env_fts_2_states():
    env = transys.FTS()
    env.states.add_from({'e0', 'e1'})
    env.states.initial.add('e0')
    
    # Park as an env action
    env.actions.add_from({'park', 'go'})
    
    env.transitions.add_labeled('e0', 'e0', 'park')
    env.transitions.add_labeled('e0', 'e0', 'go')
    
    #env.plot()
    return env

def parking_spec():
    # barely realizable: assumption necessary
    env_prog = '! (eact = park)'
    
    sys_vars = {'X0reach'}
    sys_init = {'X0reach'}
    sys_prog = {'home'}
    
    # one additional requirement: if in lot,
    # then stay there until park signal is turned off
    sys_safe = {'(X (X0reach) <-> lot) || (X0reach && !(eact = park) )',
                '((lot & (eact = park) ) -> X(lot))'}
    sys_prog |= {'X0reach'}
    
    specs = spec.GRSpec(sys_vars=sys_vars, sys_init=sys_init,
                        sys_safety=sys_safe,
                        env_prog=env_prog, sys_prog=sys_prog)
    return specs

def test_sys_fts_bool_states():
    """Sys FTS has 2 states, must become 2 bool vars in GR(1)
    """
    sys = sys_fts_2_states()
    
    spec = synth.sys_to_spec(sys)
    
    assert('loc' not in spec.sys_vars)
    assert('eloc' not in spec.sys_vars)
    
    assert('X0' in spec.sys_vars)
    assert(spec.sys_vars['X0'] == 'boolean')
    
    assert('X1' in spec.sys_vars)
    assert(spec.sys_vars['X1'] == 'boolean')

def test_env_fts_bool_states():
    """Env FTS has 2 states, must become 2 bool vars in GR(1).
    """
    env = env_fts_2_states()
    
    spec = synth.env_to_spec(env)
    
    assert('loc' not in spec.env_vars)
    assert('eloc' not in spec.env_vars)
    
    assert('e0' in spec.env_vars)
    assert(spec.env_vars['e0'] == 'boolean')
    
    assert('e1' in spec.env_vars)
    assert(spec.env_vars['e1'] == 'boolean')

def test_sys_fts_int_states():
    """Sys FTS has 3 states, must become 1 int var in GR(1).
    """
    sys = sys_fts_2_states()
    sys.states.add('X2')
    
    spec = synth.sys_to_spec(sys)
    
    assert('X0' not in spec.sys_vars)
    assert('X1' not in spec.sys_vars)
    assert('X2' not in spec.sys_vars)
    
    assert('eloc' not in spec.sys_vars)
    assert('loc' in spec.sys_vars)
    assert(spec.sys_vars['loc'] == (0, 2))

def test_env_fts_int_states():
    """Env FTS has 3 states, must become 1 int var in GR(1).
    """
    env = env_fts_2_states()
    env.states.add('e2')
    
    spec = synth.env_to_spec(env)
    
    assert('e0' not in spec.env_vars)
    assert('e1' not in spec.env_vars)
    assert('e2' not in spec.env_vars)
    
    assert('loc' not in spec.env_vars)
    assert('eloc' in spec.env_vars)
    assert(spec.env_vars['eloc'] == (0, 2))

def test_sys_fts_no_actions():
    """sys FTS has no actions.
    """
    sys = sys_fts_2_states()
    
    spec = synth.sys_to_spec(sys)
    
    assert('act' not in spec.sys_vars)

def test_env_fts_bool_actions():
    """Env FTS has 2 actions, must become 2 bool vars in GR(1).
    """
    env = env_fts_2_states()
    
    spec = synth.env_to_spec(env)
    
    assert('act' not in spec.env_vars)
    assert('eact' not in spec.env_vars)
    
    assert('park' in spec.env_vars)
    assert(spec.env_vars['park'] == 'boolean')
    
    assert('go' in spec.env_vars)
    assert(spec.env_vars['go'] == 'boolean')
 
def test_env_fts_int_actions():
    """Env FTS has 3 actions, must become 1 int var in GR(1).
    """
    env = env_fts_2_states()
    env.actions.add('stop')
    
    spec = synth.env_to_spec(env)
    
    assert('park' not in spec.env_vars)
    assert('go' not in spec.env_vars)
    assert('stop' not in spec.env_vars)
    
    assert('act' not in spec.env_vars)
    assert('eact' in spec.env_vars)    
    
    assert(set(spec.env_vars['eact']) == {'park', 'go', 'stop', 'none'})
