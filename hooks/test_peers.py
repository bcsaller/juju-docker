from mock import patch
import unittest


from peers import cli_peers


class TestPeers(unittest.TestCase):
    @patch('peers.get_peers')
    def test_peers_1unit(self, mpeers):
        mpeers.return_value = []
        result = cli_peers()
        self.assertEqual(result, '')

    @patch('peers.get_peers')
    def test_peers_3units(self, mpeers):
        mpeers.return_value = ['10.0.0.10', '10.0.0.11']
        result = cli_peers()
        self.assertEqual(result,
                         '--join 10.0.0.10:29015 --join 10.0.0.11:29015')


if __name__ == '__main__':
    unittest.main()
