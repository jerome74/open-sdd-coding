# Generate Functional Requirements and Technical Specifications from a Proposal

## Inputs

- **X — Functional Requirements Template:** `[file name or path]`
- **Y — Technical Specifications Template:** `[file name or path]`
- **Z — Technical and Commercial Proposal:** `[file name or path]`
- **Output language:** `[English]`

## Objective

Read the Technical and Commercial Proposal Z, including any available
appendices, and produce two separate documents in this order:

1. A Functional Requirements Document based on Z, using template X.
2. A Technical Specifications Document based on the Functional Requirements
   Document, using template Y. Refer directly to Z for technical commitments
   and constraints.

## 1. Generate the Functional Requirements Document using template X

- Follow template X's structure, headings, section order, and numbering
  conventions.
- Extract the actors, capabilities, workflows, business rules, integrations,
  and constraints that affect the expected behavior of the solution.
- Assign each requirement a stable identifier. Describe the expected
  behavior and define verifiable acceptance criteria in the relevant
  sections of the template.
- Trace each requirement to Z. Cite the source section and, where available,
  the page, table, or appendix.
- Distinguish explicit commitments from optional items, exclusions, and
  interpretations that require confirmation. Include commercial terms
  where they determine whether a capability is in scope or when it applies.
- Record missing or ambiguous information as open points and identify the
  requirements affected.

## 2. Generate the Technical Specifications Document using template Y

- Follow template Y's structure, headings, section order, and conventions.
- Use the Functional Requirements Document as the basis for the design.
  Consult Z for technical commitments, constraints, and documented
  architecture decisions.
- Where relevant, specify the architecture, components, interfaces, data
  flows, error handling, security controls, deployment, and verification
  approach.
- Link each design element to the requirement IDs it addresses. Cite Z
  directly for technical commitments and constraints stated in the proposal.
- Label design choices introduced while drafting as **Proposed Design**
  and explain which requirements and constraints justify them. Label
  unresolved decisions as **To Be Confirmed**.
- For each requirement with incomplete technical coverage, explain the
  gap and identify the information or decision needed to close it.

## Verification and Delivery

Verify traceability from **proposal Z → functional requirement →
technical specification**. Check that each document follows its
respective template and that every functional requirement has technical
coverage or a documented gap.

Deliver two separate files in the formats of their respective templates.
In the delivery summary, link to both files and list the open points that
affect validation or implementation.

If an essential input is missing or unreadable, identify the affected
file, complete the sections supported by the available inputs, and state
which sections remain incomplete and why.