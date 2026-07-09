# Observation source-locator labeling

A **convention** for the `name` of a `scilit-observation`: a short, human-legible code
that says *where in the paper the evidence lives*, so a curator or reader can jump
straight to the display item without opening the note. It is deliberately terse and
uniform.

> This is a convention, **not a schema constraint.** Nothing in TypeDB parses or
> enforces the code. The observation's real key is its `scobs-…` id; the label is the
> `name` attribute, and the full text always lives in `content`. The CLI validates the
> label loosely and *warns* on a malformed one — it never blocks curation.

## Why it exists

An observation already carries two kinds of provenance:

- **verbatim text** — one or more fragments via `alh-derivation` (the exact sentence(s)).
- **the measurement design** — a KEfED experiment (`kefed-model`) via the data instance.

The source-locator adds a third, orthogonal axis: **the display item a human should look
at** (Figure 3B, Table 2, Supplemental Figure 4, or "text-only"). Text spans tell you
*what was written*; the KEfED link tells you *how it was measured*; the locator tells you
*where to look in the PDF*.

## Grammar

```
label   = "O" source ( "+" source )*

source  = [ "S" ] type [ number ] [ panels ]
  S      = supplemental / supporting-information flag
  type   = "F"  main figure
         | "T"  table
         | "E"  experiment  (a result with no dedicated display item — reported in text/Methods)
         | "X"  free text / narrative (discussion assertion, no figure/table/experiment)
  number = one or more digits (figure / table / experiment number; omit for a lone "X")
  panels = one or more uppercase panel letters; a contiguous run may use a range, e.g. "D-F"
```

- `O` = observation (the note kind).
- Multiple loci join with `+` when a single measurement-in-context is read off more than
  one place.
- **Legacy form:** the original SIRT3 seed used a **bare figure digit** — `O4DF` meaning
  Figure 4, panels D & F (i.e. the `F` was implicit). Still accepted; new curation should
  write it explicitly as `OF4DF`.

## Examples

| label | reads as |
|-------|----------|
| `OF1AC` | Figure 1, panels A & C |
| `OF4D-F` | Figure 4, panels D through F |
| `OSF3B` | **Supplemental** Figure 3, panel B |
| `OT2` | Table 2 |
| `OST1` | Supplemental Table 1 |
| `OE5` | **Experiment 5** — a result reported only in text/Methods, no figure/table |
| `OX` | stated only in the narrative (e.g. a Discussion assertion) |
| `OF2A+SF4C` | Figure 2A **and** Supplemental Figure 4C together |

## Choosing the locus

1. **Prefer the most specific display item** that actually shows the result:
   main figure panel > supplemental figure panel > table.
2. **No display item?** If the result is stated only in prose or Methods, use `E<n>`
   pointing at the reconstructed KEfED experiment (its figure/experiment index). If it is
   not tied to any reconstructed experiment (a bare narrative assertion), use `X`.
3. **Supplemental** material takes the leading `S` flag: `SF`, `ST`.
4. **Panels are the paper's own panel letters** — list only the panels that carry *this*
   observation, not every panel in the figure.
5. **One observation = one measurement-in-context.** If one panel yields two distinct
   measurements-in-context, they become two observations that may share a locator (the
   label is a locator, not a unique key — the `scobs-…` id disambiguates).

## Producing it

CLI:

```bash
scientific-literature add-observation --bundle <scsense-…> \
  --statement "SIRT3 overexpression: 5-fold increase in functional reconstitution of aged HSCs" \
  --knowledge-level assertion --bio-scale tissue \
  --source-label OF4DF
```

Library (`kqed.py`):

```python
add_observation(driver, bundle, statement, "assertion", "tissue", source_label="OF4DF")
```

When `--source-label` / `source_label=` is supplied it becomes the observation `name`
verbatim; the full statement is stored in `content` either way. Omit it and the name falls
back to the truncated statement (prior behavior).
