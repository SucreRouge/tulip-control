# Copyright (c) 2012, 2013 by California Institute of Technology
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 
# 3. Neither the name of the California Institute of Technology nor
#    the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior
#    written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL CALTECH
# OR THE CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
"""
Interface to library of synthesis tools, e.g., JTLV, gr1c
"""
import logging
logger = logging.getLogger(__name__)

from warnings import warn

from tulip import transys
from tulip.spec import GRSpec
from tulip import jtlvint
from tulip import gr1cint

hl = '\n' +60*'-'

def pstr(s):
    return '(' +str(s) +')'

def _disj(set0):
    return " || ".join([
        "(" +str(x) +")"
        for x in set0
    ])

def _conj(set0):
    return " && ".join([
        "(" +str(x) +")"
        for x in set0
    ])

def _conj_intersection(set0, set1, parenth=True):
    if parenth:
        return " && ".join([
            "("+str(x)+")"
            for x in set0
            if x in set1
        ])
    else:
        return " && ".join([
            str(x)
            for x in set0
            if x in set1
        ])

def _conj_neg(set0, parenth=True):
    if parenth:
        return " && ".join([
            "!("+str(x)+")"
            for x in set0
        ])
    else:
        return " && ".join([
            "!"+str(x)
            for x in set0
        ])

def _conj_neg_diff(set0, set1, parenth=True):
    if parenth:
        return " && ".join([
            "!("+str(x)+")"
            for x in set0
            if x not in set1
        ])
    else:
        return " && ".join([
            "!"+str(x)
            for x in set0
            if x not in set1
        ])

def mutex(iterable):
    """Mutual exclusion for all time.
    """
    iterable = filter(lambda x: x != '', iterable)
    if not iterable:
        return []
    if len(iterable) <= 1:
        return []
    
    return [_conj([
        '!(' + str(x) + ') || (' + _conj_neg_diff(iterable, [x]) +')'
        for x in iterable
    ]) ]

def exactly_one(iterable):
    """N-ary xor.
    
    Contrast with pure mutual exclusion.
    """
    if len(iterable) <= 1:
        return [pstr(x) for x in iterable]
    
    return ['(' + _disj([
        '(' +str(x) + ') && ' + _conj_neg_diff(iterable, [x])
        for x in iterable
    ]) + ')']

def _conj_action(label, action_type, nxt=False, ids=None):
    if action_type not in label:
        return ''
    action = label[action_type]
    if ids is not None:
        action = ids[action]
    if action is '':
        return ''
    if nxt:
        return ' && X' + pstr(action)
    else:
        return ' && ' + pstr(action)

def create_states(states, variables, trans, statevar, bool_states):
    """Create bool or int state variables in GR(1).
    
    Return map of TS states to spec variable valuations.
    
    @param states: TS states
    
    @param variables: to be augmented with state variables
    
    @param trans: to be augmented with state variable constraints.
        Such a constraint is necessary only in case of bool states.
        It requires that exactly one bool variable be True at a time.
    
    @param statevar: name to use for int-valued state variabe.
    
    @param bool_states: if True, then use bool variables.
        Otherwise use int-valued variable.
        The latter is overridden in case < 3 states exist,
        to avoid issues with gr1c.
    """
    # too few states for a gr1c int variable ?
    if len(states) < 3:
        bool_states = True
    
    if bool_states:
        state_ids = {x:x for x in states}
        variables.update({s:'boolean' for s in states})
        trans += exactly_one(states)
    else:
        state_ids, domain = states2ints(states, statevar)
        variables[statevar] = domain
    return state_ids

def states2ints(states, statevar):
    """Return states of form 'statevar = #'.
    
    where # is obtained by dropping the 1st char
    of each given state.
    
    @type states: iterable of str,
        each str of the form: letter + number
    
    @param statevar: name of int variable representing
        the current state
    @type statevar: str
    
    @rtype: {state : state_id}
    """
    # TODO: merge with actions2ints, don't strip letter
    
    letter_int = True
    for state in states:
        try:
            int(state[1:])
        except:
            letter_int = False
            break
    
    if letter_int:
        # this allows the user to control numbering
        strip_letter = lambda x: statevar + ' = ' + x[1:]
        state_ids = {x:strip_letter(x) for x in states}
        n_states = len(states)
        domain = (0, n_states-1)
    else:
        setloc = lambda s: statevar + ' = ' + s
        state_ids = {s:setloc(s) for s in states}
        domain = list(states)
    
    return (state_ids, domain)

def create_actions(
    actions, variables, trans, init,
    actionvar, bool_actions, actions_must
):
    """Represent actions by bool or int GR(1) variables.
    
    Similar to the int representation of states.
    
    If the actions are:
    
       - mutually exclusive (use_mutex == True)
       - bool actions have not been requested (bool_actions == False)
      
    then an int variable represents actions in GR(1).
    
    If actions are not mutually exclusive,
    then only bool variables can represent them.
    
    Suppose N actions are defined.
    The int variable is allowed to take N+1 values.
    The additional value corresponds to all actions being False.
    
    If FTS actions are integers,
    then the additional action is an int value.
    
    If FTS actions are strings (e.g., 'park', 'wait'),
    then the additional action is 'none'.
    They are treated by gr1cint as an arbitrary finite domain.
    
    An option 'min_one' is internally available,
    in order to allow only N values of the action variable.
    This requires that at least one action be True each time.
    Combined with a mutex constraint, it yields an n-ary xor constraint.
    
    @return: mapping from FTS actions, to GR(1) actions.
        If bools are used, then GR(1) are the same.
        Otherwise, they map to e.g. 'act = wait'
    @rtype: dict
    """
    if not actions:
        return
    
    logger.debug('create actions:' + str(actions) )
    
    # options for modeling actions
    if actions_must is None:
        use_mutex = False
        min_one = False
    elif actions_must == 'mutex':
        use_mutex = True
        min_one = False
    elif actions_must == 'xor':
        use_mutex = True
        min_one = True
    else:
        raise Exception('Unknown value: actions_must = ' +
                        str(actions_must) )
    
    # too few values for gr1c ?
    #if len(actions) < 3:
    #    bool_actions = True
    
    # no mutex -> cannot use int variable
    if not use_mutex:
        bool_actions = True
    
    if bool_actions:
        logger.debug('bool actions')
        
        action_ids = {x:x for x in actions}
        variables.update({a:'boolean' for a in actions})
        
        # single action ?
        if not mutex(action_ids.values()):
            return action_ids
        
        if use_mutex and not min_one:
            trans += ['X (' + mutex(action_ids.values())[0] + ')']
            init += mutex(action_ids.values())
        elif use_mutex and min_one:
            trans += ['X (' + exactly_one(action_ids.values())[0] + ')']
            init += exactly_one(action_ids.values())
        elif min_one:
            raise Exception('min_one requires mutex')
    else:
        assert(use_mutex)
        action_ids, domain = actions2ints(actions, actionvar, min_one)
        variables[actionvar] = domain
    return action_ids

def actions2ints(actions, actionvar, min_one=False):
    int_actions = True
    for action in actions:
        if not isinstance(action, int):
            int_actions = False
            break
    if int_actions:
        action_ids = {x:x for x in actions}
        n_actions = len(actions)
        
        # extra value modeling all False ?
        if min_one:
            n = n_actions -1
        else:
            n = n_actions
        domain = (0, n)
    else:
        setact = lambda s: actionvar + ' = ' + s
        action_ids = {s:setact(s) for s in actions}
        domain = list(actions)
        if not min_one:
            domain += [actionvar + 'none']
        
    return (action_ids, domain)

def sys_to_spec(
    sys, ignore_initial, bool_states,
    action_vars, bool_actions, actions_must
):
    """Convert system's transition system to GR(1) representation.
    
    The term GR(1) representation is preferred to GR(1) spec,
    because an FTS can represent sys_init, sys_safety, but
    not other spec forms.
    
    @type sys: transys.FTS | transys.OpenFTS
    
    @param ignore_initial: Do not include initial state info from TS.
        Enable this to mask absence of OpenFTS initial states.
        Useful when initial states are specified in another way,
        e.g., directly augmenting the spec part.
    @type check_initial_exist: bool
    
    @param bool_states: if True,
        then use one bool variable for each state,
        otherwise use an int variable called loc.
    @type bool_states: bool
    
    @rtype: GRSpec
    """
    if isinstance(sys, transys.FiniteTransitionSystem):
        (sys_vars, sys_init, sys_trans) = fts2spec(
            sys, ignore_initial, bool_states, 'loc',
            action_vars[1], bool_actions, actions_must
        )
        return GRSpec(sys_vars=sys_vars, sys_init=sys_init,
                      sys_safety=sys_trans)
    elif isinstance(sys, transys.OpenFiniteTransitionSystem):
        return sys_open_fts2spec(
            sys, ignore_initial, bool_states,
            action_vars, bool_actions, actions_must
        )
    else:
        raise TypeError('synth.sys_to_spec does not support ' +
            str(type(sys)) +'. Use FTS or OpenFTS.')

def env_to_spec(
    env, ignore_initial, bool_states,
    action_vars, bool_actions, actions_must
):
    """Convert environment transition system to GR(1) representation.
    
    For details see also sys_to_spec.
    
    @type env: transys.FTS | transys.OpenFTS
    
    @type bool_states: bool
    """
    if isinstance(env, transys.FiniteTransitionSystem):
        (env_vars, env_init, env_trans) = fts2spec(
            env, ignore_initial, bool_states, 'eloc',
            action_vars[0], bool_actions, actions_must
        )
        return GRSpec(env_vars=env_vars, env_init=env_init,
                      env_safety=env_trans)
    elif isinstance(env, transys.OpenFiniteTransitionSystem):
        return env_open_fts2spec(
            env, ignore_initial, bool_states,
            action_vars, bool_actions, actions_must
        )
    else:
        raise TypeError('synth.env_to_spec does not support ' +
            str(type(env)) +'. Use FTS or OpenFTS.')

def fts2spec(
    fts, ignore_initial=False, bool_states=False,
    statevar='loc', actionvar='act',
    bool_actions=False, actions_must=None
):
    """Convert closed FTS to GR(1) representation.
    
    So fts on its own is not the complete problem spec.
    
    @param fts: transys.FiniteTransitionSystem
    
    @rtype: GRSpec
    """
    assert(isinstance(fts, transys.FiniteTransitionSystem))
    
    aps = fts.aps
    states = fts.states
    actions = fts.actions
    
    sys_init = []
    sys_trans = []
    
    sys_vars = {ap:'boolean' for ap in aps}
    
    action_ids = create_actions(
        actions, sys_vars, sys_trans, sys_init,
        actionvar, bool_actions, actions_must
    )
    
    state_ids = create_states(states, sys_vars, sys_trans,
                              statevar, bool_states)
    
    sys_init += sys_init_from_ts(states, state_ids, aps, ignore_initial)
    
    sys_trans += sys_trans_from_ts(
        states, state_ids, fts.transitions,
        action_ids=action_ids
    )
    sys_trans += ap_trans_from_ts(states, state_ids, aps)
    
    return (sys_vars, sys_init, sys_trans)

def sys_open_fts2spec(
    ofts, ignore_initial=False, bool_states=False,
    action_vars=None, bool_actions=False, actions_must=None
):
    """Convert OpenFTS to GR(1) representation.
    
    Note that not any GR(1) can be represented by an OpenFTS,
    as the OpenFTS is currently defined.
    A GameStructure would be needed instead.
    
    Use the spec to add more information,
    for example to specify env_init, sys_init that
    involve both sys_vars and env_vars.
    
    For example, an OpenFTS cannot represent how the
    initial valuation of env_vars affects the allowable
    initial valuation of sys_vars, which is represented
    by the state of OpenFTS.
    
    Either OpenFTS can be extended in the future,
    or a game structure added.
    
    notes
    -----
    
    1. Currently each env_action becomes a bool env_var.
        In the future a candidate option is to represent the
        env_actions as an enumeration.
        This would avoid the exponential cost incurred by bools.
        A map between the enum and named env_actions
        will probably also be needed.
    
    @param ofts: transys.OpenFiniteTransitionSystem
    
    @rtype: GRSpec
    """
    assert(isinstance(ofts, transys.OpenFiniteTransitionSystem))
    
    aps = ofts.aps
    states = ofts.states
    trans = ofts.transitions
    env_actions = ofts.env_actions
    sys_actions = ofts.sys_actions
    
    sys_init = []
    sys_trans = []
    env_init = []
    env_trans = []
    
    sys_vars = {ap:'boolean' for ap in aps}
    env_vars = dict()
    
    sys_action_ids = create_actions(
        sys_actions, sys_vars, sys_trans, sys_init,
        action_vars[1], bool_actions, actions_must
    )
    
    env_action_ids = create_actions(
        env_actions, env_vars, env_trans, env_init,
        action_vars[0], bool_actions, actions_must
    )
    
    statevar = 'loc'
    state_ids = create_states(states, sys_vars, sys_trans,
                              statevar, bool_states)
    
    sys_init += sys_init_from_ts(states, state_ids, aps, ignore_initial)
    
    sys_trans += sys_trans_from_ts(
        states, state_ids, trans,
        sys_action_ids=sys_action_ids, env_action_ids=env_action_ids
    )
    sys_trans += ap_trans_from_ts(states, state_ids, aps)
    
    env_trans += env_trans_from_sys_ts(
        states, state_ids, trans, env_action_ids
    )
    
    return GRSpec(
        sys_vars=sys_vars, env_vars=env_vars,
        env_init=env_init, sys_init=sys_init,
        env_safety=env_trans, sys_safety=sys_trans
    )

def env_open_fts2spec(
    ofts, ignore_initial=False, bool_states=False,
    action_vars=None, bool_actions=False, actions_must=None
):
    assert(isinstance(ofts, transys.OpenFiniteTransitionSystem))
    
    aps = ofts.aps
    states = ofts.states
    trans = ofts.transitions
    env_actions = ofts.env_actions
    sys_actions = ofts.sys_actions
    
    sys_init = []
    sys_trans = []
    env_init = []
    env_trans = []
    
    # since APs are tied to env states, let them be env variables
    env_vars = {ap:'boolean' for ap in aps}
    sys_vars = dict()
    
    env_action_ids = create_actions(
        env_actions, env_vars, env_trans, env_init,
        action_vars[0], bool_actions, actions_must
    )
    
    # some duplication here, because we don't know
    # whether the user will provide a system TS as well
    # and whether that TS will contain all the system actions
    # defined in the environment TS
    sys_action_ids = create_actions(
        sys_actions, sys_vars, sys_trans, sys_init,
        action_vars[1], bool_actions, actions_must
    )
    
    statevar = 'eloc'
    state_ids = create_states(states, env_vars, env_trans,
                              statevar, bool_states)
    
    env_init += sys_init_from_ts(states, state_ids, aps, ignore_initial)
    
    env_trans += env_trans_from_env_ts(
        states, state_ids, trans,
        env_action_ids=env_action_ids, sys_action_ids=sys_action_ids
    )
    env_trans += ap_trans_from_ts(states, state_ids, aps)
    
    return GRSpec(
        sys_vars=sys_vars, env_vars=env_vars,
        env_init=env_init, sys_init=sys_init,
        env_safety=env_trans, sys_safety=sys_trans
    )

def sys_init_from_ts(states, state_ids, aps, ignore_initial=False):
    """Initial state, including enforcement of exactly one.
    
    APs also considered for the initial state.
    """
    init = []
    
    # don't ignore labeling info
    for state in states.initial:
        state_id = state_ids[state]
        label = states.label_of(state)
        ap_str = sprint_aps(label, aps)
        if not ap_str:
            continue
        init += ['!(' + pstr(state_id) + ') || (' + ap_str +')']
    
    # skip ?
    if ignore_initial:
        return init
    
    if not states.initial:
        msg = 'FTS has no initial states.\n'
        msg += 'Enforcing this renders False the GR(1):\n'
        msg += ' - guarantee if this is a system TS,\n'
        msg += '   so the spec becomes trivially False.\n'
        msg += ' - assumption if this is an environment TS,\n'
        msg += '   so the spec becomes trivially True.'
        warn(msg)
        
        init += ['False']
        return init
        
    init += [_disj([state_ids[s] for s in states.initial])]
    return init

def sys_trans_from_ts(
    states, state_ids, trans,
    action_ids=None, sys_action_ids=None, env_action_ids=None):
    """Convert transition relation to GR(1) sys_safety.
    
    The transition relation may be closed or open,
    i.e., depend only on system, or also on environment actions.
    
    @type trans: FiniteTransitionSystem.transitions |
        OpenFiniteTransitionSystem.transitions
    
    No mutexes enforced by this function among:
        
        - sys states
        - env actions
    """
    sys_trans = []
    
    # Transitions
    for from_state in states:
        from_state_id = state_ids[from_state]
        precond = pstr(from_state_id)
        
        cur_trans = trans.find([from_state])
        
        # no successor states ?
        if not cur_trans:
            sys_trans += [precond + ' -> X(False)']
            continue
        
        cur_str = []
        for (from_state, to_state, label) in cur_trans:
            to_state_id = state_ids[to_state]
            
            postcond = pstr(to_state_id)
            
            postcond += _conj_action(label, 'env_actions', ids=env_action_ids)
            postcond += _conj_action(label, 'sys_actions', ids=sys_action_ids)
            # system FTS given
            postcond += _conj_action(label, 'actions', ids=action_ids)
            
            cur_str += [postcond]
            
        sys_trans += [precond + ' -> X(' + _disj(cur_str) + ')']
    return sys_trans

def env_trans_from_sys_ts(states, state_ids, trans, env_action_ids):
    """Convert environment actions to GR(1) env_safety.
    
    This constrains the actions available next to the environment
    based on the system OpenFTS.
    
    Might become optional in the future,
    depending on the desired way of defining env behavior.
    """
    env_trans = []
    if not env_action_ids:
        return env_trans
    
    for from_state in states:
        from_state_id = state_ids[from_state]
        precond = pstr(from_state_id)
        
        cur_trans = trans.find([from_state])
        
        # no successor states ?
        if not cur_trans:
            env_trans += [precond + ' -> X(' +
                _conj_neg(env_action_ids.values() ) + ')']
            continue
        
        # collect possible next env actions
        next_env_actions = set()
        for (from_state, to_state, label) in cur_trans:
            if 'env_actions' not in label:
                continue
            
            env_action = label['env_actions']
            env_action_id = env_action_ids[env_action]
            next_env_actions.add(env_action_id)
        next_env_actions = _disj(next_env_actions)
        
        env_trans += [precond + ' -> X(' +
                      next_env_actions + ')']
    return env_trans

def env_trans_from_env_ts(
    states, state_ids, trans,
    action_ids=None, env_action_ids=None, sys_action_ids=None
):
    """Convert environment TS transitions to GR(1) representation.
    
    This contributes to the \rho_e(X, Y, X') part of the spec,
    i.e., constrains the next environment state variables' valuation
    depending on the previous environment state variables valuation
    and the previous system action (system output).
    """
    env_trans = []
    
    for from_state in states:
        from_state_id = state_ids[from_state]
        precond = pstr(from_state_id)
        
        cur_trans = trans.find([from_state])
        
        # no successor states ?
        if not cur_trans:
            env_trans += [precond + ' -> X(False)']
                
            msg = 'Environment dead-end found.\n'
            msg += 'If sys can force env to dead-end,\n'
            msg += 'then GR(1) assumption becomes False,\n'
            msg += 'and spec trivially True.'
            warn(msg)
            
            continue
        
        cur_list = []
        found_free = False # any environment transition
        # not conditioned on the previous system output ?
        for (from_state, to_state, label) in cur_trans:
            to_state_id = state_ids[to_state]
            
            postcond = 'X' + pstr(to_state_id)
            
            postcond += _conj_action(label, 'env_actions', nxt=True,
                                     ids=env_action_ids)
            
            # environment FTS given
            postcond += _conj_action(label, 'actions', nxt=True, ids=action_ids)
            postcond += _conj_action(label, 'sys_actions', ids=sys_action_ids)
            
            if not _conj_action(label, 'sys_actions', ids=sys_action_ids):
                found_free = True
            
            cur_list += [pstr(postcond) ]
        
        # can sys kill env by setting all previous sys outputs to False ?
        # then env assumption becomes False,
        # so the spec trivially True: avoid this
        if not found_free and sys_action_ids:
            cur_list += [_conj_neg(sys_action_ids.values() )]
        
        env_trans += [pstr(precond) + ' -> (' + _disj(cur_list) +')']
    return env_trans

def ap_trans_from_ts(states, state_ids, aps):
    """Require atomic propositions to follow states according to label.
    """
    trans = []
    
    # no AP labels ?
    if not aps:
        return trans
    
    for state in states:
        label = states.label_of(state)
        state_id = state_ids[state]
        
        tmp = sprint_aps(label, aps)
        if not tmp:
            continue
        
        trans += ["X(("+ str(state_id) +") -> ("+ tmp +"))"]
    return trans

def sprint_aps(label, aps):
    if label.has_key("ap"):
        tmp0 = _conj_intersection(aps, label['ap'], parenth=False)
    else:
        tmp0 = ''
    
    if label.has_key("ap"):
        tmp1 = _conj_neg_diff(aps, label['ap'], parenth=False)
    else:
        tmp1 = _conj_neg(aps, parenth=False)
    
    if len(tmp0) > 0 and len(tmp1) > 0:
        tmp = tmp0 +' && '+ tmp1
    else:
        tmp = tmp0 + tmp1
    return tmp

def synthesize(
    option, specs, env=None, sys=None,
    ignore_env_init=False, ignore_sys_init=False,
    bool_states=False, action_vars=None,
    bool_actions=False, actions_must='xor',
    verbose=0
):
    """Function to call the appropriate synthesis tool on the spec.

    Beware!  This function provides a generic interface to a variety
    of routines.  Being under active development, the types of
    arguments supported and types of objects returned may change
    without notice.

    @param option: Magic string that declares what tool to invoke,
        what method to use, etc.  Currently recognized forms:

          - C{"gr1c"}: use gr1c for GR(1) synthesis via L{gr1cint}.
          - C{"jtlv"}: use JTLV for GR(1) synthesis via L{jtlvint}.
    @type specs: L{spec.GRSpec}
    
    @param env: A transition system describing the environment:
        
            - states controlled by environment
            - input: sys_actions
            - output: env_actions
            - initial states constrain the environment
        
        This constrains the transitions available to
        the environment, given the outputs from the system.
        
        Note that an OpenFTS with only sys_actions is
        equivalent to an FTS for the environment.
    @type env: transys.FTS | transys.OpenFTS
    
    @param sys: A transition system describing the system:
        
            - states controlled by the system
            - input: env_actions
            - output: sys_actions
            - initial states constrain the system
        
        Note that an OpenFTS with only sys_actions is
        equivalent to an FTS for the system.
    @type sys: transys.FTS | transys.OpenFTS
    
    @param ignore_sys_init: Ignore any initial state information
        contained in env.
    @type ignore_sys_init: bool
    
    @param ignore_env_init: Ignore any initial state information
        contained in sys.
    @type ignore_env_init: bool
    
    @param bool_states: if True,
        then use one bool variable for each state.
        Otherwise use a single int variable for all states.
        
        Currently int state implemented only for gr1c.
    @type bool_states: bool
    
    @param action_vars: for the integer variables modeling
        environment and system actions in GR(1).
        Effective only when >2 actions for each player.
    @type action_vars: 2-tuple of str:
        
            (env_action_var_name, sys_action_var_name)
        
        Default: ('eact', 'act')
        
        (must be valid variable name)
    
    @param bool_actions: model actions using bool variables
    @type bool_actions: bool
    
    @param actions_must: select constraint one actions. Options:
        
            - 'mutex': at most 1 action True each time
            - 'xor': exactly 1 action True each time
            - None: no constraint on action values
        
        The xor constraint can prevent the environment from
        blocking the system by setting all its actions to False.
    
    @type actions_must: 'mutex' | 'xor' | None
    
    @type verbose: bool
    
    @return: If spec is realizable,
        then return a Mealy machine implementing the strategy.
        Otherwise return None.
    @rtype: transys.MealyMachine | None
    """
    bool_states, action_vars, bool_actions = _check_solver_options(
        option, bool_states, action_vars, bool_actions
    )
    
    specs = spec_plus_sys(specs, env, sys,
                          ignore_env_init, ignore_sys_init,
                          bool_states, action_vars,
                          bool_actions, actions_must)
    
    if option == 'gr1c':
        ctrl = gr1cint.synthesize(specs, verbose=verbose)
    elif option == 'jtlv':
        ctrl = jtlvint.synthesize(specs, verbose=verbose)
    else:
        raise Exception('Undefined synthesis option. '+\
                        'Current options are "jtlv" and "gr1c"')
    
    try:
        logger.debug('Mealy machine has: n = ' +
            str(len(ctrl.states) ) +' states.')
    except:
        logger.debug('No Mealy machine returned.')
    
    # no controller found ?
    # exploring unrealizability with counterexamples or other means
    # can be done by calling a dedicated other function, not this
    if not isinstance(ctrl, transys.MealyMachine):
        return None
    
    return ctrl

def is_realizable(
    option, specs, env=None, sys=None,
    ignore_env_init=False, ignore_sys_init=False,
    bool_states=False, action_vars=None,
    bool_actions=False, actions_must='xor',
    verbose=0
):
    """Check realizability.
    
    For details see synthesize.
    """
    bool_states, action_vars, bool_actions = _check_solver_options(
        option, bool_states, action_vars, bool_actions
    )
    
    specs = spec_plus_sys(
        specs, env, sys,
        ignore_env_init, ignore_sys_init,
        bool_states, action_vars, bool_actions, actions_must
    )
    
    if option == 'gr1c':
        r = gr1cint.check_realizable(specs, verbose=verbose)
    elif option == 'jtlv':
        r = jtlvint.check_realizable(specs, verbose=verbose)
    else:
        raise Exception('Undefined synthesis option. '+\
                        'Current options are "jtlv" and "gr1c"')
    return r

def _check_solver_options(option, bool_states, action_vars, bool_actions):
    if action_vars is None:
        action_vars = _default_action_vars()
    
    if bool_states is False and option is 'jtlv':
        warn('Int state not yet available for jtlv solver.\n' +
             'Using bool states.')
        bool_states = True
    
    if bool_actions is False and option is 'jtlv':
        warn('Int action modeling not yet available for jtlv solver.\n' +
             'Using bool actions.')
        bool_actions = True
    
    return (bool_states, action_vars, bool_actions)

def _default_action_vars():
    return ('eact', 'act')

def spec_plus_sys(
    specs, env, sys,
    ignore_env_init, ignore_sys_init,
    bool_states, action_vars, bool_actions, actions_must
):
    if sys is not None:
        sys_formula = sys_to_spec(sys, ignore_sys_init, bool_states,
                                  action_vars, bool_actions, actions_must)
        specs = specs | sys_formula
        logger.debug('sys TS:\n' + str(sys_formula.pretty() ) + hl)
    if env is not None:
        env_formula = env_to_spec(env, ignore_env_init, bool_states,
                                  action_vars, bool_actions, actions_must)
        specs = specs | env_formula
        logger.debug('env TS:\n' + str(env_formula.pretty() ) + hl)
        
    logger.info('Overall Spec:\n' + str(specs.pretty() ) +hl)
    return specs

def import_PropPreservingPartition(self, disc_dynamics,
                                       cont_varname="cellID"):
    """Append results of discretization (abstraction) to specification.

    disc_dynamics is an instance of PropPreservingPartition, such
    as returned by the function discretize in module discretize.

    Notes
    =====
      - The cell names are *not* mangled, in contrast to the
        approach taken in the createProbFromDiscDynamics method of
        the SynthesisProb class.

      - Any name in disc_dynamics.list_prop_symbol matching a system
        variable is removed from sys_vars, and its occurrences in
        the specification are replaced by a disjunction of
        corresponding cells.

      - gr1c does not (yet) support variable domains beyond Boolean,
        so we treat each cell as a separate Boolean variable and
        explicitly enforce mutual exclusion.
    """
    if len(disc_dynamics.list_region) == 0:  # Vacuous call?
        return
    cont_varname += "_"  # ...to make cell number easier to read
    for i in range(len(disc_dynamics.list_region)):
        if (cont_varname+str(i)) not in self.sys_vars:
            self.sys_vars.append(cont_varname+str(i))

    # The substitution code and transition code below are mostly
    # from createProbFromDiscDynamics and toJTLVInput,
    # respectively, in the rhtlp module, with some style updates.
    for prop_ind, prop_sym in enumerate(disc_dynamics.list_prop_symbol):
        reg = [j for j in range(len(disc_dynamics.list_region))
               if disc_dynamics.list_region[j].list_prop[prop_ind] != 0]
        if len(reg) == 0:
            subformula = "False"
            subformula_next = "False"
        else:
            subformula = " | ".join([
                cont_varname+str(regID) for regID in reg
            ])
            subformula_next = " | ".join([
                cont_varname+str(regID)+"'" for regID in reg
            ])
        prop_sym_next = prop_sym+"'"
        self.sym_to_prop(props={prop_sym_next:subformula_next})
        self.sym_to_prop(props={prop_sym:subformula})

    # Transitions
    for from_region in range(len(disc_dynamics.list_region)):
        to_regions = [i for i in range(len(disc_dynamics.list_region))
                      if disc_dynamics.trans[i][from_region] != 0]
        self.sys_safety.append(cont_varname+str(from_region) + " -> (" +
            " | ".join([cont_varname+str(i)+"'" for i in to_regions]) + ")")

    # Mutex
    self.sys_init.append("")
    self.sys_safety.append("")
    for regID in range(len(disc_dynamics.list_region)):
        if len(self.sys_safety[-1]) > 0:
            self.sys_init[-1] += "\n| "
            self.sys_safety[-1] += "\n| "
        self.sys_init[-1] += "(" + cont_varname+str(regID)
        if len(disc_dynamics.list_region) > 1:
            self.sys_init[-1] += " & " + " & ".join([
                "(!"+cont_varname+str(i)+")"
                for i in range(len(disc_dynamics.list_region)) if i != regID
            ])
        self.sys_init[-1] += ")"
        self.sys_safety[-1] += "(" + cont_varname+str(regID)+"'"
        if len(disc_dynamics.list_region) > 1:
            self.sys_safety[-1] += " & " + " & ".join([
                "(!"+cont_varname+str(i)+"')"
                for i in range(len(disc_dynamics.list_region)) if i != regID
            ])
        self.sys_safety[-1] += ")"
