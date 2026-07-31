"""Vulture whitelist: names it cannot know are used by design.

Protocol method parameters (``charter_core.ports``) exist for documentation
and static signature-checking, not implementation -- vulture sees an
unused local variable where there is really an interface contract. Referencing
each name here as a fake attribute access is vulture's documented whitelist
idiom: it makes the name "used" without changing runtime behaviour, since this
file is never imported by anything else.
"""

base_head_or_pr_or_sha = None
base_head_or_pr_or_sha.base
base_head_or_pr_or_sha.head
base_head_or_pr_or_sha.pr_number
base_head_or_pr_or_sha.sha
