# Literature Trends — Schema Reference

Types marked **`<<literature-trends>>`** are new in this skill.
All other types are inherited from `alhazen_notebook.tql`.

---

## Diagram A — Collections, Entities, Relations, and Notes

The entity type hierarchy rooted at `identifiable-entity`, the two literature-trends
extensions (`trend-thread`, `trend-hypothesis-note`), and the structural relations that
connect them.

```mermaid
classDiagram
    direction TB

    class IdentifiableEntity["identifiable-entity"] {
        <<abstract>>
        id : string
        name : string
        description : string
        created-at : datetime
        provenance : string
        source-uri : string
    }

    class Collection["collection"] {
        logical-query : string
        is-extensional : boolean
    }

    class TrendThread["trend-thread"] {
        <<literature-trends>>
        trend-keyword : string
        trend-window : string
    }

    class DomainThing["domain-thing"] {
    }

    class InformationContentEntity["information-content-entity"] {
        <<abstract>>
        content : string
        format : string
        cache-path : string
        token-count : integer
    }

    class Note["note"] {
        confidence : double
    }

    class TrendHypothesisNote["trend-hypothesis-note"] {
        <<literature-trends>>
        abductive-role : string
        trend-window : string
    }

    class Tag["tag"] {
        id : string
        name : string
    }

    %% ── Inheritance ──────────────────────────────────────────────────────────
    IdentifiableEntity <|-- Collection
    IdentifiableEntity <|-- DomainThing
    IdentifiableEntity <|-- InformationContentEntity
    Collection          <|-- TrendThread
    InformationContentEntity <|-- Note
    Note                <|-- TrendHypothesisNote

    %% ── Structural relations ─────────────────────────────────────────────────
    %% label = TypeDB relation type name; role names shown as multiplicity labels
    Collection          "collection"  -->  "member *"      IdentifiableEntity : collection-membership
    Collection          "parent"      -->  "child *"       Collection         : collection-nesting
    Note                "note"        -->  "subject"       IdentifiableEntity : aboutness
    Note                "parent-note" -->  "child-note *"  Note               : note-threading
    Note                "claim"       -->  "evidence *"    Note               : evidence-chain
    IdentifiableEntity                -->  "tag"           Tag                : tagging
    TrendHypothesisNote "predecessor" -->  "successor"     TrendHypothesisNote : hypothesis-genealogy
```

### Relation attribute ownership (Diagram A)

| Relation | Roles | Owned attributes |
|---|---|---|
| `collection-membership` | `collection` → `member` | `created-at`, `provenance` |
| `collection-nesting` | `parent-collection` → `child-collection` | — |
| `aboutness` | `note` → `subject` | — |
| `note-threading` | `parent-note` → `child-note` | — |
| `evidence-chain` | `claim` → `evidence` | `confidence`, `evidence-type-attr` |
| `tagging` | `tagged-entity` → `tag` | `created-at`, `provenance` |
| `hypothesis-genealogy` | `predecessor` → `successor` | `genealogy-type`, `confidence`, `provenance`, `description` |

> **`hypothesis-genealogy`** is the only entirely new relation type in this skill.
> All other relations are defined in `alhazen_notebook.tql` and reused here.

---

## Diagram B — Artifacts, Fragments, and Connected Notes

The `information-content-entity` branch and the relations that define the
content capture pipeline: how artifacts are acquired from external sources,
decomposed into fragments, and annotated with notes.

```mermaid
classDiagram
    direction TB

    class InformationContentEntity["information-content-entity"] {
        <<abstract>>
        content : string
        content-hash : string
        format : string
        cache-path : string
        mime-type : string
        file-size : integer
        token-count : integer
    }

    class Artifact["artifact"] {
    }

    class Fragment["fragment"] {
        offset : integer
        length : integer
    }

    class Note["note"] {
        confidence : double
    }

    class TrendHypothesisNote["trend-hypothesis-note"] {
        <<literature-trends>>
        abductive-role : string
        trend-window : string
    }

    class IdentifiableEntity["identifiable-entity"] {
        <<abstract>>
        id : string
        name : string
    }

    class DomainThing["domain-thing"] {
    }

    class Agent["agent"] {
        agent-type : string
        model-name : string
    }

    %% ── Inheritance ──────────────────────────────────────────────────────────
    InformationContentEntity <|-- Artifact
    InformationContentEntity <|-- Fragment
    InformationContentEntity <|-- Note
    Note                     <|-- TrendHypothesisNote
    IdentifiableEntity       <|-- DomainThing
    DomainThing              <|-- Agent

    %% ── Content pipeline relations ───────────────────────────────────────────
    Artifact                "artifact"   -->  "referent"  DomainThing              : representation
    Artifact                "whole"      -->  "part *"    Fragment                 : fragmentation
    Fragment                "quoting"    -->  "quoted"    Fragment                 : quotation
    InformationContentEntity "derivative" --> "source"   InformationContentEntity : derivation
    Agent                   "author"     -->  "work"      InformationContentEntity : authorship
    Note                    "note"       -->  "subject"   IdentifiableEntity       : aboutness
```

### Relation summary (Diagram B)

| Relation | Roles | Description |
|---|---|---|
| `representation` | `artifact` → `referent` | Links a captured artifact to the domain-thing it represents |
| `fragmentation` | `whole` → `part` | Decomposes an artifact into fragments |
| `quotation` | `quoting-fragment` → `quoted-fragment` | Cross-reference between fragments |
| `derivation` | `derivative` → `derived-from-source` | Provenance chain for derived content |
| `authorship` | `author` → `work` | Attribution of any ICE to an agent or author |
| `aboutness` | `note` → `subject` | Connects a note to any identifiable entity |

---

## Position of `trend-hypothesis-note` across both diagrams

`trend-hypothesis-note` inherits from `note` → `information-content-entity` → `identifiable-entity`,
placing it in both diagrams simultaneously:

**In Diagram A (collections / notes context):**
- Stored in a `trend-thread` collection via `collection-membership`
- Linked to a source paper collection via `aboutness`
- Chained to predecessor/successor hypotheses via `hypothesis-genealogy`
- Can be threaded with follow-up notes via `note-threading`
- Supported by evidence notes via `evidence-chain`

**In Diagram B (artifacts / fragments context):**
- Inherits `content`, `format`, `cache-path`, `token-count` from `information-content-entity`
- Can be traced back to source artifacts via `derivation`
- Can be attributed to an agent (Claude) via `authorship`

The `abductive-role` and `trend-window` attributes are the only additions this skill makes
to the `note` type; everything else is inherited or reused from the base schema.
