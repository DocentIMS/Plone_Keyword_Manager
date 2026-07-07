# DCWorkflow Expressions in Plone

A practical reference for writing TALES expressions in Zope/DCWorkflow — the
engine behind Plone's `portal_workflow`. It explains **what each expression
context actually is**, **when it is available**, and **how to use it**, with
worked examples and a fully annotated `definition.xml`.

> Scope note: this document is general Plone/DCWorkflow knowledge. The Keyword
> Manager product does not ship a custom workflow, but the same rules apply to
> any workflow you add to a Plone site.

---

## 1. The big picture: where expressions live and when they run

DCWorkflow expressions are [TALES](https://zope.readthedocs.io/en/latest/zopebook/AppendixC.html)
expressions (the same language used in Zope Page Templates — `python:`,
`path:`, `string:`, `nocall:`, `not:` …). They appear in three places:

1. **Guards** — on *transitions*, *worklists*, and (rarely) *states*. A guard
   combines an optional **Condition** expression (must evaluate truthy) with
   permission / role / group checks. Guards decide whether a user may *see* and
   *use* a transition.
2. **Variables** — the "Variables" tab. Each variable has a **Default
   Expression** that computes its value when a transition fires. If the
   variable is marked *"store in state"* the computed value is saved into the
   object's per-object workflow status.
3. **Worklists** — expressions that filter which objects appear in a user's
   task list.

The single most important thing to understand:

> **Guard expressions and variable expressions run at different moments, so they
> have different contexts available.**

- A **guard/condition** runs *before* a transition — often merely to render the
  UI ("is this action available?"). At that point **there is no `state_change`,
  no `new_state`, no `transition`** yet (the transition has not happened). You
  mainly have `here`, `container`, `user`, `portal`.
- A **variable default expression** runs *during* transition execution, so the
  full `state_change` object and its friends (`transition`, `old_state`,
  `new_state`, `status`) are populated.

That asymmetry is the most common cause of "why does my expression blow up with
a `KeyError` / `AttributeError`?" — you referenced a variable-time context
inside a guard. See [§6 Pitfalls](#6-common-pitfalls).

---

## 2. The base contexts

These behave slightly differently from the same names in page templates:

| Name | What it is | Notes |
|------|------------|-------|
| `here` | **The content object** being acted on | *Not* the workflow object. `here/getId`, `here/Title`, `here/portal_type`, `here/absolute_url` all work. Same object as `state_change.object`. |
| `container` | The content object's **container** (`aq_parent`) | The folder `here` lives in. Useful for parent-dependent guards. |

Several other contexts are always provided:

| Name | What it is |
|------|------------|
| `transition` | The `TransitionDefinition` being executed. `transition/getId` → e.g. `'publish'`. |
| `status` | Mapping of the **former** per-object status (incl. every variable marked *store in state*, plus `review_state`). Same data as `state_change.status`. |
| `workflow` | The `DCWorkflowDefinition` object itself (the thing defined in `definition.xml`). |
| `scripts` | The scripts folder of the workflow — lets an expression **call** a workflow script, e.g. `python: scripts.my_guard(here, transition)`. |
| `user` | The authenticated member (also available). `user/getId`, `user/getRoles`. |
| `portal` | The portal root (site root). |

`scripts` is the escape hatch: when an expression gets too gnarly to write on
one line, push the logic into a workflow script and call it. That is the
recommended pattern for anything non-trivial (see [§5](#5-when-to-use-scripts-instead)).

---

## 3. The `state_change` object — the workhorse

During transition execution you get a rich `state_change` object. Many of its
attributes duplicate the base contexts above; they exist so a workflow **script**
(which receives only `state_change`) can reach everything.

### Attributes

| Attribute | What it is |
|-----------|------------|
| `state_change.object` | the content object — **same as `here`** |
| `state_change.workflow` | the workflow definition — **same as `workflow`** |
| `state_change.transition` | the transition — **same as `transition`** |
| `state_change.status` | mapping of the **former** status (incl. stored variables) — **same as `status`** |
| `state_change.old_state` | the source `StateDefinition`; `old_state.getId()` → e.g. `'private'` |
| `state_change.new_state` | the destination `StateDefinition`; `new_state.getId()` → e.g. `'published'` |
| `state_change.kwargs` | keyword args passed to `doActionFor(ob, action, **kw)` (this is where a transition *comment* arrives) |

### Methods

| Method | Returns |
|--------|---------|
| `state_change.getHistory()` | a **copy** of the object's workflow history (list of dicts: `action`, `actor`, `time`, `comments`, `review_state`, …). Decide based on past transitions. |
| `state_change.getPortal()` | the portal root — reach site-wide tools/settings. |
| `state_change.getDateTime()` | the `DateTime` of *this* transition — the canonical way to stamp a `time` variable. |

### Exceptions you can raise (from scripts)

| Exception | Raise it when… |
|-----------|----------------|
| `state_change.ObjectDeleted` | your script **deleted** the object (e.g. a "reject" that removes it), so the engine does not try to write status back onto a gone object. |
| `state_change.ObjectMoved` | your script **moved/renamed** the object, so the engine re-finds it and completes the transition at the new location. |

---

## 4. The `old_state` / `state` / `status` word-clash

DCWorkflow stores the **name** of the current state *inside* the status mapping
under the `review_state` key — the state is **not** a first-class attribute of
the content object. So these read like synonyms but are three distinct things:

- `state_change.old_state` — a **state object** → `.getId()` gives the name.
- `state_change.status['review_state']` — the **name string** of the former state.
- `status` (the context) — the whole **mapping**, not a state.

This is the "unfortunate word clash" the DCWorkflow docs warn about. Internalise
it and a whole class of confusing bugs disappears.

---

## 5. Worked examples

### The standard action/actor/time/comments variable set

This is exactly how Plone's built-in workflows populate the history log. On the
**Variables** tab (or in `definition.xml`):

| Variable | Default expression |
|----------|--------------------|
| `action` | `transition/getId|nothing` |
| `actor` | `user/getId` |
| `time` | `state_change/getDateTime` |
| `comments` | `python: state_change.kwargs.get('comment', '')` |
| `review_state` | *(stored automatically as the new state name)* |

The `|nothing` fallback in `transition/getId|nothing` matters: on the **initial**
state (object creation) there is *no* transition, so `transition` is missing —
the fallback prevents a traceback. This is the guard-vs-variable timing issue in
miniature.

### A guard condition (content-dependent access)

Guards usually lean on the permission/role/group fields for access control and
reserve the *expression* for content-dependent checks:

```
python: here.portal_type != 'Image' or here.Subject()
```

"You can't publish an image unless it has been tagged." Note it only touches
`here` — safe to evaluate before the transition.

### A parent-dependent guard

```
python: here.portal_workflow.getInfoFor(container, 'review_state') == 'published'
```

"Only allow publishing when the containing folder is itself published."

### Recording the previous state in a variable

```
python: state_change.old_state.getId()
```

### Branching a variable on which transition fired

```
python: 'Published' if transition.getId() == 'publish' else 'Draft'
```

---

## 6. When to use scripts instead

When an expression exceeds one readable line, move the logic into a **workflow
script** and either bind it as an *after-transition script* or call it from an
expression via `scripts`:

```
python: scripts.check_can_publish(here, transition)
```

A workflow script (a Script (Python) under the workflow, or an External Method)
receives the full `state_change` as its single argument, so you get the entire
context as real Python:

```python
# script bound as an after-transition script on "publish"
def notify_on_publish(state_change):
    obj = state_change.object
    portal = state_change.getPortal()
    if state_change.new_state.getId() == 'published':
        portal.MailHost.send(
            messageText='%s was published by %s' % (
                obj.Title(), state_change.kwargs.get('actor', 'someone')),
            mto='editors@example.com',
        )
```

---

## 7. Common pitfalls

1. **Referencing transition-time contexts in a guard.** `state_change`,
   `new_state`, and `transition` may be **absent** when the UI is just checking
   whether an action is available. Guard only on `here` / `container` / `user` /
   `portal`, or add `|nothing` fallbacks.
2. **Forgetting the initial-state case.** On object creation there is no
   transition — always use `transition/getId|nothing` (or a `python:` guard on
   `.get(...)`).
3. **Confusing state name vs state object** — see [§4](#4-the-old_state--state--status-word-clash).
   `old_state` is an object; `status['review_state']` is a string.
4. **Doing access control in expressions.** Prefer permissions/roles/groups —
   they are auditable and faster. Reserve expressions for content-dependent
   logic.
5. **Writing status back after delete/move.** If a script deletes or moves the
   object, raise `state_change.ObjectDeleted` / `ObjectMoved` so the engine does
   not error trying to persist status.

---

## 8. Where this lives in a modern Plone product (GenericSetup)

In modern Plone you define workflows declaratively rather than clicking them into
the ZMI. The file is:

```
profiles/default/workflows/<workflow_id>/definition.xml
```

and you register it in `profiles/default/workflows.xml`. The same TALES strings
described above go into `<guard-expression>` and `<default-expression>` elements.

### Annotated `definition.xml`

```xml
<?xml version="1.0"?>
<dc-workflow
    workflow_id="my_review_workflow"
    title="My Review Workflow"
    description="Two-state review workflow demonstrating guards, stored
                 variables, and an after-transition script."
    state_variable="review_state"
    initial_state="private"
    manager_bypass="False">

  <!-- ============ PERMISSIONS managed by this workflow ============ -->
  <permission>Access contents information</permission>
  <permission>View</permission>
  <permission>Modify portal content</permission>

  <!-- ============================ STATES ========================== -->
  <state state_id="private" title="Private">
    <description>Only owners and reviewers can see the item.</description>
    <exit-transition transition_id="publish"/>
    <!-- Permission map: which roles get which permission in this state -->
    <permission-map name="View" acquired="False">
      <permission-role>Manager</permission-role>
      <permission-role>Owner</permission-role>
      <permission-role>Reviewer</permission-role>
    </permission-map>
  </state>

  <state state_id="published" title="Published">
    <description>Visible to everyone.</description>
    <exit-transition transition_id="retract"/>
    <permission-map name="View" acquired="True">
      <permission-role>Anonymous</permission-role>
    </permission-map>
  </state>

  <!-- ========================= TRANSITIONS ======================== -->
  <transition transition_id="publish"
              title="Publish"
              new_state="published"
              trigger="USER"
              before_script=""
              after_script="notify_on_publish">
    <description>Make the item visible to everyone.</description>
    <action url="%(content_url)s/content_status_modify?workflow_action=publish"
            category="workflow">Publish</action>
    <!-- GUARD: permission AND a content-dependent condition.
         The expression touches only `here`, so it is safe pre-transition. -->
    <guard>
      <guard-permission>Review portal content</guard-permission>
      <guard-expression>
        python: here.portal_type != 'Image' or here.Subject()
      </guard-expression>
    </guard>
  </transition>

  <transition transition_id="retract"
              title="Retract"
              new_state="private"
              trigger="USER"
              before_script=""
              after_script="">
    <description>Take the item back out of public view.</description>
    <action url="%(content_url)s/content_status_modify?workflow_action=retract"
            category="workflow">Retract</action>
    <guard>
      <guard-permission>Modify portal content</guard-permission>
    </guard>
  </transition>

  <!-- ========================== VARIABLES ========================= -->
  <!-- Standard history-log variables. `update_always` recomputes them on
       every transition; `for_status="True"` stores them in per-object state. -->
  <variable variable_id="action" for_catalog="False"
            for_status="True" update_always="True">
    <description>The last transition that fired.</description>
    <default>
      <expression>transition/getId|nothing</expression>
    </default>
    <guard/>
  </variable>

  <variable variable_id="actor" for_catalog="False"
            for_status="True" update_always="True">
    <description>The user who performed the last transition.</description>
    <default>
      <expression>user/getId</expression>
    </default>
    <guard/>
  </variable>

  <variable variable_id="time" for_catalog="False"
            for_status="True" update_always="True">
    <description>When the last transition happened.</description>
    <default>
      <expression>state_change/getDateTime</expression>
    </default>
    <guard/>
  </variable>

  <variable variable_id="comments" for_catalog="False"
            for_status="True" update_always="True">
    <description>Comment entered with the transition.</description>
    <default>
      <expression>python:state_change.kwargs.get('comment', '')</expression>
    </default>
    <guard/>
  </variable>

  <variable variable_id="review_history" for_catalog="False"
            for_status="False" update_always="False">
    <description>The full workflow history.</description>
    <default>
      <expression>state_change/getHistory</expression>
    </default>
    <!-- Only owners/reviewers may read the history -->
    <guard>
      <guard-permission>Request review</guard-permission>
      <guard-permission>Review portal content</guard-permission>
    </guard>
  </variable>

  <!-- ========================= WORKLISTS ========================== -->
  <!-- Objects that a reviewer should act on. -->
  <worklist worklist_id="reviewer_queue" title="Pending review">
    <description>Items waiting to be published.</description>
    <action url="%(portal_url)s/search?review_state=private"
            category="global">Pending (%(count)d)</action>
    <guard>
      <guard-permission>Review portal content</guard-permission>
    </guard>
    <match name="review_state" values="private"/>
  </worklist>

</dc-workflow>
```

Key attributes to note:

- **`state_variable="review_state"`** — the status key that holds the state name
  (the "word clash" from §4 in XML form).
- **`for_status="True"`** on a variable — this is the *"store in state"* checkbox;
  the value lands in `status` / `state_change.status`.
- **`after_script="notify_on_publish"`** — binds a workflow script that receives
  `state_change` and runs *after* the transition commits (see §6).
- **`guard-expression`** — the TALES condition; combined with `guard-permission`
  / `guard-role` / `guard-group` by logical AND.

---

## 9. Quick reference card

| I want to… | Use |
|------------|-----|
| Read the content object | `here` / `state_change.object` |
| Read its folder | `container` |
| Know which transition fired | `transition/getId` |
| Know the previous state name | `state_change/old_state/getId` or `status['review_state']` |
| Know the destination state name | `state_change/new_state/getId` |
| Get the transition's timestamp | `state_change/getDateTime` |
| Get the transition comment | `python:state_change.kwargs.get('comment', '')` |
| Read the history | `state_change/getHistory` |
| Reach the site root | `portal` / `state_change/getPortal` |
| Call complex logic | `scripts.<name>(...)` or an after-transition script |
| Survive the initial (no-transition) state | append `|nothing` to the expression |
