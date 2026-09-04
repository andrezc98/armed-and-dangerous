#!/usr/bin/env bash
# Stub. Completed in Task 10: greps results/assets/scripts for account IDs,
# sensitive ARNs and credentials before anything is committed.
# Must print "sanitize-check: clean" when the tree is safe.
#
# TODO (Task 10): results/<date>/cluster.json and results/<date>/ecr.json carry
# the sandbox account id and are git-ignored for that reason. The check must
# assert they are still ignored (`git check-ignore -q`) rather than only grep
# the tracked tree, because a `git add -f` is exactly the mistake it exists to
# catch. results/images.json is the opposite case: committed on purpose, and it
# must NOT contain a 12-digit account id or a *.dkr.ecr.* host.
echo "sanitize-check: stub (Task 10)"