import os
import tempfile
import unittest

import config


class CommentFunctionsTests(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.db_fd)
        config.DB_NAME = self.db_path
        config.init_database()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_add_and_get_comments(self):
        created = config.add_comment('demo-model', 'Great benchmark', username='Tester', session_id='session-1')
        self.assertIn('id', created)
        self.assertEqual(created['comment'], 'Great benchmark')

        comments = config.get_comments('demo-model')
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments.iloc[0]['comment'], 'Great benchmark')
        self.assertEqual(comments.iloc[0]['username'], 'Tester')

    def test_build_comment_tree_for_replies(self):
        parent = config.add_comment('demo-model', 'Parent comment', username='Tester', session_id='session-1')
        reply = config.add_comment('demo-model', 'Reply comment', username='Other', session_id='session-2', parent_id=parent['id'])

        tree = config.build_comment_tree('demo-model')
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]['id'], parent['id'])
        self.assertEqual(len(tree[0]['replies']), 1)
        self.assertEqual(tree[0]['replies'][0]['id'], reply['id'])
        self.assertEqual(tree[0]['replies'][0]['parent_id'], parent['id'])


if __name__ == '__main__':
    unittest.main()
