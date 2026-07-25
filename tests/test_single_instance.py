import time
import unittest
import uuid

from PySide6.QtCore import QCoreApplication

from app.single_instance import ActivationServer, request_activation


class ActivationServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.name = f"AirPoint-test-{uuid.uuid4().hex}"
        self.server = ActivationServer(self.name)

    def tearDown(self):
        self.server.close()
        self.app.processEvents()

    def test_connecting_requests_activation(self):
        activations = []
        self.server.activation_requested.connect(lambda: activations.append(True))
        self.assertTrue(self.server.listen())

        self.assertTrue(request_activation(self.name, timeout_ms=250))
        deadline = time.monotonic() + 0.5
        while not activations and time.monotonic() < deadline:
            self.app.processEvents()

        self.assertEqual(activations, [True])

    def test_multiple_launches_each_request_activation(self):
        activations = []
        self.server.activation_requested.connect(lambda: activations.append(True))
        self.assertTrue(self.server.listen())

        self.assertTrue(request_activation(self.name, timeout_ms=250))
        self.assertTrue(request_activation(self.name, timeout_ms=250))
        deadline = time.monotonic() + 0.5
        while len(activations) < 2 and time.monotonic() < deadline:
            self.app.processEvents()

        self.assertEqual(len(activations), 2)

    def test_missing_server_fails_without_false_success(self):
        self.assertFalse(request_activation(self.name, timeout_ms=25))


if __name__ == "__main__":
    unittest.main()
