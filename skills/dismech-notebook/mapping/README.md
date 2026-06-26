# DisMech -> Alhazen Notebook Mapping Rules

GLAV mapping from the `dismech` TypeDB database to `dm-*` types in `alhazen_notebook`.

## Rule Phases

**Phase 1 - Standalone entities (no foreign keys):**
- `01_disease` - disease -> dm-disease
- `02_gene_descriptor` - genedescriptor -> dm-gene-descriptor
- `03_phenotype_descriptor` - phenotypedescriptor -> dm-phenotype-descriptor
- `04_disease_descriptor` - diseasedescriptor -> dm-disease-descriptor
- `05_anatomical_descriptor` - anatomicalentitydescriptor -> dm-anatomical-descriptor
- `06_celltype_descriptor` - celltypedescriptor -> dm-celltype-descriptor
- `07_process_descriptor` - biologicalprocessdescriptor -> dm-process-descriptor
- `08_papers` - evidenceitem PMIDs -> scilit-paper stubs

**Phase 2 - Disease-linked entities:**
- `10_mechanism` - pathophysiology -> dm-mechanism + dm-disease-has-mechanism
- `11_phenotype` - phenotype -> dm-phenotype + dm-disease-has-phenotype
- `12_genetic` - genetic -> dm-genetic + dm-disease-has-genetic
- `13_treatment` - treatment -> dm-treatment + dm-disease-has-treatment
- `15_disease_term` - disease-term -> dm-disease-term-link

**Phase 3 - Mechanism substructure:**
- `20_causal_edge` - causaledge -> dm-causal-edge + dm-mechanism-downstream
- `21_mechanism_gene` - gene -> dm-gene-annotation
- `22_mechanism_location` - locations -> dm-mechanism-location
- `23_mechanism_celltype` - cell-types -> dm-mechanism-celltype
- `24_mechanism_process` - biological-processes -> dm-mechanism-process
- `25_phenotype_term` - phenotype-term -> dm-phenotype-term

**Phase 4 - Evidence:**
- `30_evidence_notes` - evidenceitem -> dm-evidence-note + aboutness + dm-evidence-citation
- `31_findings` - finding -> dm-finding-note + aboutness

## Running

```bash
uv run python src/skillful_alhazen/utils/schema_mapper.py run \
  --source-db dismech \
  --target-db alhazen_notebook \
  --rules-dir plugins/dismech/skills/dismech-notebook/mapping/rules \
  --dry-run
```
