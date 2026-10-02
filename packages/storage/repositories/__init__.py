"""Concrete repository implementations.

Empty in Phase 1 by design: the corpus tables do not exist until phase 2, and writing
repositories against a schema that does not exist would mean guessing it twice.

What is worth noticing about what is *not* here: no ``Unfiltered`` or ``AsSystem``
repository variant. Every read path takes a :class:`~core.auth.principal.Principal`,
including administrative and evaluation reads. Corpus-wide operations that genuinely need
to bypass access control are expressed at the route layer with an operator role and an
audit record, so that bypass is always attributable to a named actor.

Phase 2 adds ``document_repository.py`` and ``chunk_repository.py`` here.
"""
