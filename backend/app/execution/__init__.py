"""Doing the work: Newt's approved actions carried out in the firm's own systems, confirmed, and followed up.

executor      how an action reaches a system (signed webhook) or is simulated when none is connected
destinations  the systems a team connects, each with its own signing secret
routines      which actions Newt runs for each decision, approved by the mentor (an earned responsibility)
service       queue, run, retry, confirm, complete, fail, follow up
"""
