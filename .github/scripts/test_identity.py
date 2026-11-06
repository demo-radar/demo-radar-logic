import unittest
from check_identity import check_commit, check_login

class IdentityTests(unittest.TestCase):
    def test_wrong_account_cannot_create_or_update_a_pull_request(self):
        check_login('roygrssmn', 'actor')
        check_login('dependabot[bot]', 'actor')
        with self.assertRaises(ValueError):
            check_login('roy-nfisch', 'actor')

    def test_wrong_commit_author_and_committer_are_rejected(self):
        commit = {'sha': 'fixture', 'commit': {
            'author': {'email': 'roy@grossman.im'},
            'committer': {'email': 'roy@grossman.im'}}}
        check_commit(commit)
        commit['commit']['author']['email'] = 'roy424+neuefische@gmail.com'
        with self.assertRaises(ValueError):
            check_commit(commit)
        commit['commit']['author']['email'] = 'roy@grossman.im'
        commit['commit']['committer']['email'] = 'roy424+neuefische@gmail.com'
        with self.assertRaises(ValueError):
            check_commit(commit)

    def test_github_merge_provenance_is_preserved(self):
        check_commit({'sha': 'fixture', 'commit': {
            'author': {'email': 'roy@grossman.im'},
            'committer': {'email': 'noreply@github.com'}}})

if __name__ == '__main__':
    unittest.main()
