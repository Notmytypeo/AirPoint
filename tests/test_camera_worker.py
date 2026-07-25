import unittest
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from app.camera_worker import (
    AdaptiveInferenceScheduler,
    CameraWorker,
    FaceOverlapFilter,
    StartupActivationGate,
)
from app.gestures import GestureAction, HandObservation, Landmark
from app.tuning import normalized_tuning


def fake_result(name="Right"):
    point = SimpleNamespace(x=0.1, y=0.2, z=0.0)
    category = SimpleNamespace(category_name=name, display_name="")
    return SimpleNamespace(hand_landmarks=[[point] * 21], handedness=[[category]])


def duplicate_handedness_result():
    category = SimpleNamespace(category_name="Left", display_name="")
    left_side = [SimpleNamespace(x=0.20, y=0.2, z=0.0)] * 21
    right_side = [SimpleNamespace(x=0.80, y=0.2, z=0.0)] * 21
    return SimpleNamespace(hand_landmarks=[left_side, right_side], handedness=[[category], [category]])


class CameraWorkerTests(unittest.TestCase):
    @staticmethod
    def _candidate(center_x, center_y, handedness="Right"):
        points = tuple(
            Landmark(center_x + ((index % 5) - 2) * 0.012, center_y + ((index // 5) - 2) * 0.012)
            for index in range(21)
        )
        return HandObservation(handedness, points, points, 0.9)

    def test_new_hand_skeleton_contained_by_face_is_rejected(self):
        candidate_filter = FaceOverlapFilter()
        face = ((0.20, 0.10, 0.50, 0.65),)
        candidate = self._candidate(0.45, 0.45)
        self.assertEqual(candidate_filter.apply((candidate,), face, 1.0), ())

    def test_face_match_invalidates_even_a_continuous_real_hand_track(self):
        candidate_filter = FaceOverlapFilter()
        face = ((0.20, 0.10, 0.50, 0.65),)
        acquired = self._candidate(0.73, 0.45)
        crossing = self._candidate(0.62, 0.45)
        self.assertEqual(candidate_filter.apply((acquired,), face, 1.0), (acquired,))
        self.assertEqual(candidate_filter.apply((crossing,), face, 1.1), ())
        self.assertNotIn("right", candidate_filter._accepted)

        # Moving back out of the face region cannot revive the old track; two
        # independent clean source frames are required again.
        emerged = self._candidate(0.73, 0.45)
        self.assertEqual(
            candidate_filter.apply((emerged,), (), 1.14, scan_captured_at=1.13),
            (),
        )
        self.assertEqual(
            candidate_filter.apply((emerged,), (), 1.18, scan_captured_at=1.17),
            (emerged,),
        )

    def test_stale_hand_track_does_not_whitelist_face_false_positive(self):
        candidate_filter = FaceOverlapFilter()
        face = ((0.20, 0.10, 0.50, 0.65),)
        acquired = self._candidate(0.73, 0.45)
        face_candidate = self._candidate(0.62, 0.45)
        candidate_filter.apply((acquired,), face, 1.0)
        self.assertEqual(candidate_filter.apply((face_candidate,), face, 1.5), ())

    def test_unverified_async_face_window_cannot_whitelist_a_false_hand(self):
        candidate_filter = FaceOverlapFilter()
        face = ((0.20, 0.10, 0.50, 0.65),)
        candidate = self._candidate(0.45, 0.45)
        self.assertEqual(
            candidate_filter.apply((candidate,), (), 1.0, scan_captured_at=-10.0),
            (),
        )
        self.assertTrue(candidate_filter.verification_requested())
        self.assertEqual(
            candidate_filter.apply((candidate,), face, 1.04, scan_captured_at=1.03),
            (),
        )

    def test_new_real_hand_is_accepted_after_post_arrival_face_scan(self):
        candidate_filter = FaceOverlapFilter()
        candidate = self._candidate(0.75, 0.45)
        self.assertEqual(
            candidate_filter.apply((candidate,), (), 1.0, scan_captured_at=0.9),
            (),
        )
        self.assertEqual(
            candidate_filter.apply((candidate,), (), 1.04, scan_captured_at=1.03),
            (),
        )
        self.assertEqual(
            candidate_filter.apply((candidate,), (), 1.08, scan_captured_at=1.07),
            (candidate,),
        )

    def test_one_false_negative_scan_cannot_whitelist_later_face_region(self):
        candidate_filter = FaceOverlapFilter()
        candidate = self._candidate(0.45, 0.45)
        face = ((0.20, 0.10, 0.50, 0.65),)
        self.assertEqual(
            candidate_filter.apply((candidate,), (), 1.00, scan_captured_at=0.90),
            (),
        )
        self.assertEqual(
            candidate_filter.apply((candidate,), (), 1.04, scan_captured_at=1.03),
            (),
        )
        self.assertEqual(
            candidate_filter.apply((candidate,), face, 1.08, scan_captured_at=1.07),
            (),
        )

    def test_scan_captured_before_candidate_cannot_verify_it_after_late_completion(self):
        candidate_filter = FaceOverlapFilter()
        candidate = self._candidate(0.75, 0.45)
        self.assertEqual(
            candidate_filter.apply(
                (candidate,),
                (),
                1.0,
                scan_captured_at=0.99,
            ),
            (),
        )
        # The worker may consume this scan much later, but only the source
        # frame time is relevant to candidate verification.
        self.assertEqual(
            candidate_filter.apply(
                (candidate,),
                (),
                1.10,
                scan_captured_at=0.99,
            ),
            (),
        )
        self.assertTrue(candidate_filter.verification_requested())

    def test_known_face_rejection_does_not_request_scans_every_callback(self):
        candidate_filter = FaceOverlapFilter()
        face = ((0.20, 0.10, 0.50, 0.65),)
        candidate = self._candidate(0.45, 0.45)
        for timestamp in (1.0, 1.04, 1.08, 1.12):
            self.assertEqual(
                candidate_filter.apply(
                    (candidate,),
                    face,
                    timestamp,
                    scan_captured_at=0.9,
                ),
                (),
            )
        self.assertFalse(candidate_filter.verification_requested())

    def test_adaptive_scheduler_preserves_near_30fps_camera_cadence(self):
        scheduler = AdaptiveInferenceScheduler()
        tuning = normalized_tuning({
            "adaptive_inference": 0,
            "inference_active_fps": 30,
        })
        timestamps = [index * 0.0321 for index in range(125)]
        accepted = [
            timestamp
            for timestamp in timestamps
            if scheduler.should_submit(timestamp, False, tuning)
        ]
        measured_fps = (len(accepted) - 1) / (timestamps[-1] - timestamps[0])
        self.assertGreater(measured_fps, 26.0)
        self.assertLess(measured_fps, 31.5)

    def test_adaptive_scheduler_uses_active_hold_and_busy_backpressure(self):
        scheduler = AdaptiveInferenceScheduler()
        tuning = normalized_tuning({
            "adaptive_inference": 1,
            "inference_active_fps": 30,
            "inference_idle_fps": 12,
            "inference_activity_hold": 0.5,
        })
        self.assertEqual(scheduler.target_fps(1.0, tuning), 12)
        scheduler.observe(True, 1.0, tuning)
        self.assertEqual(scheduler.target_fps(1.4, tuning), 30)
        self.assertEqual(scheduler.target_fps(1.51, tuning), 12)
        scheduler.reset()
        self.assertFalse(scheduler.should_submit(2.0, True, tuning))
        self.assertTrue(scheduler.should_submit(2.0, False, tuning))

    def test_windows_auto_exposure_uses_directshow_automatic_mode(self):
        class Capture:
            def __init__(self):
                self.calls = []

            def set(self, property_id, value):
                self.calls.append((property_id, value))
                return True

        capture = Capture()
        cv2 = SimpleNamespace(CAP_PROP_AUTO_EXPOSURE=21)
        self.assertTrue(CameraWorker._enable_windows_auto_exposure(capture, cv2))
        self.assertEqual(capture.calls, [(21, 0.75)])

    def test_unsupported_auto_exposure_is_non_fatal(self):
        class Capture:
            def set(self, _property_id, _value):
                raise ValueError("unsupported")

        cv2 = SimpleNamespace(CAP_PROP_AUTO_EXPOSURE=21)
        self.assertFalse(CameraWorker._enable_windows_auto_exposure(Capture(), cv2))

    def test_focus_lock_forces_manual_focus_and_clamps_its_value(self):
        worker = CameraWorker()
        worker.set_focus(True, 999, True)
        self.assertFalse(worker._autofocus)
        self.assertTrue(worker._focus_lock)
        self.assertEqual(worker._manual_focus, 255)
        self.assertEqual(worker._focus_revision, 1)

    def test_disabling_or_switching_releases_all_inputs_immediately(self):
        controller = SimpleNamespace(release_all=Mock())
        worker = CameraWorker()
        worker._controller = controller
        worker.set_enabled(True)
        worker.set_enabled(False)
        if worker._release_thread is not None:
            worker._release_thread.join(0.2)
        controller.release_all.assert_called_once_with()

        worker.set_camera(1)
        if worker._release_thread is not None:
            worker._release_thread.join(0.2)
        self.assertEqual(controller.release_all.call_count, 2)
        worker.set_swap_hands(False)
        if worker._release_thread is not None:
            worker._release_thread.join(0.2)
        self.assertEqual(controller.release_all.call_count, 3)

    def test_stale_callback_generation_cannot_dispatch_after_disable(self):
        controller = SimpleNamespace(left_down=Mock(), release_all=Mock())
        worker = CameraWorker()
        worker._controller = controller
        worker.set_enabled(True)
        generation = worker._control_generation
        worker.set_enabled(False)
        self.assertFalse(
            worker._dispatch_if_current((GestureAction("left_down"),), generation)
        )
        controller.left_down.assert_not_called()

    def test_camera_loss_invalidation_rejects_outstanding_callback(self):
        controller = SimpleNamespace(left_down=Mock(), release_all=Mock())
        worker = CameraWorker()
        worker._controller = controller
        worker.set_enabled(True)
        generation = worker._control_generation
        worker._invalidate_inflight_actions()
        self.assertFalse(
            worker._dispatch_if_current((GestureAction("left_down"),), generation)
        )
        controller.left_down.assert_not_called()

    def test_disable_during_slow_dispatch_releases_any_late_latch(self):
        worker = CameraWorker()

        class Controller:
            def __init__(self):
                self.releases = 0

            def left_down(self):
                worker.set_enabled(False)

            def release_all(self):
                self.releases += 1

        controller = Controller()
        worker._controller = controller
        worker.set_enabled(True)
        generation = worker._control_generation
        self.assertFalse(
            worker._dispatch_if_current((GestureAction("left_down"),), generation)
        )
        self.assertEqual(controller.releases, 1)

    def test_stale_dispatch_drains_a_pending_release_before_return(self):
        controller = SimpleNamespace(left_down=Mock(), release_all=Mock())
        worker = CameraWorker()
        worker._controller = controller
        worker.set_enabled(True)
        generation = worker._control_generation
        with worker._lock:
            worker._enabled = False
            worker._control_generation += 1
            worker._release_pending = True
        self.assertFalse(
            worker._dispatch_if_current((GestureAction("left_down"),), generation)
        )
        controller.release_all.assert_called_once_with()
        controller.left_down.assert_not_called()

    def test_queued_release_worker_does_not_reassert_a_drained_request(self):
        controller = SimpleNamespace(release_all=Mock())
        worker = CameraWorker()
        worker._controller = controller
        with worker._lock:
            worker._release_pending = True
        with worker._dispatch_lock:
            worker._drain_pending_release_locked()

        # Simulate the already-created queue worker getting CPU only after a
        # newer dispatch drained its request.
        worker._run_queued_input_release()
        controller.release_all.assert_called_once_with()
        self.assertFalse(worker._release_pending)

    def test_transient_release_failure_retries_asynchronously_with_backoff(self):
        released = threading.Event()
        attempts = []

        class Controller:
            def release_all(self):
                attempts.append(time.monotonic())
                if len(attempts) < 3:
                    raise RuntimeError("temporary backend failure")
                released.set()

        worker = CameraWorker()
        worker._controller = Controller()
        started = time.monotonic()
        worker._queue_input_release()
        self.assertLess(time.monotonic() - started, 0.05)
        self.assertTrue(released.wait(0.50))
        release_thread = worker._release_thread
        if release_thread is not None:
            release_thread.join(0.20)

        self.assertEqual(len(attempts), 3)
        self.assertGreaterEqual(attempts[1] - attempts[0], 0.01)
        self.assertGreaterEqual(attempts[2] - attempts[1], 0.02)
        self.assertFalse(worker._release_pending)

    def test_dispatch_exception_still_releases_a_late_latch(self):
        worker = CameraWorker()

        class Controller:
            def __init__(self):
                self.releases = 0

            def left_down(self):
                worker.set_enabled(False)

            def volume(self, _direction):
                raise RuntimeError("injected action failure")

            def release_all(self):
                self.releases += 1

        controller = Controller()
        worker._controller = controller
        worker.set_enabled(True)
        generation = worker._control_generation
        with self.assertRaisesRegex(RuntimeError, "injected action failure"):
            worker._dispatch_if_current(
                (
                    GestureAction("left_down"),
                    GestureAction("volume", amount=1),
                ),
                generation,
            )
        self.assertEqual(controller.releases, 1)

    def test_stop_surfaces_qthread_timeout(self):
        worker = CameraWorker()
        worker.wait = Mock(return_value=False)
        worker.requestInterruption = Mock()
        self.assertFalse(worker.stop(timeout_ms=25))
        worker.requestInterruption.assert_called_once_with()
        worker.wait.assert_called_once_with(25)

    def test_stop_zero_timeout_never_enters_qthread_wait(self):
        worker = CameraWorker()
        worker.isRunning = Mock(return_value=True)
        worker.wait = Mock(side_effect=AssertionError("GUI stop must not wait"))
        worker.requestInterruption = Mock()
        self.assertFalse(worker.stop())
        worker.requestInterruption.assert_called_once_with()
        worker.isRunning.assert_called_once_with()
        worker.wait.assert_not_called()

    def test_stop_zero_timeout_reports_an_already_stopped_worker(self):
        worker = CameraWorker()
        worker.isRunning = Mock(return_value=False)
        worker.wait = Mock(side_effect=AssertionError("GUI stop must not wait"))
        self.assertTrue(worker.stop(timeout_ms=0))
        worker.wait.assert_not_called()

    def test_stop_timeout_is_not_blocked_by_busy_dispatch_lock(self):
        worker = CameraWorker()
        worker._controller = SimpleNamespace(release_all=Mock())
        worker.wait = Mock(return_value=False)
        worker.requestInterruption = Mock()
        worker._dispatch_lock.acquire()
        try:
            started = time.monotonic()
            self.assertFalse(worker.stop(timeout_ms=25))
            elapsed = time.monotonic() - started
        finally:
            worker._dispatch_lock.release()
        self.assertLess(elapsed, 0.10)
        worker.wait.assert_called_once_with(25)

    def test_stop_timeout_is_not_blocked_by_stalled_controller_release(self):
        release_gate = threading.Event()
        release_started = threading.Event()

        class Controller:
            def release_all(self):
                release_started.set()
                release_gate.wait(1.0)

        worker = CameraWorker()
        worker._controller = Controller()
        worker.wait = Mock(return_value=False)
        worker.requestInterruption = Mock()
        started = time.monotonic()
        try:
            self.assertFalse(worker.stop(timeout_ms=25))
            self.assertLess(time.monotonic() - started, 0.10)
            self.assertTrue(release_started.wait(0.20))
            worker.wait.assert_called_once_with(25)
        finally:
            release_gate.set()

    def test_stop_consumes_qualified_startup_activation(self):
        worker = CameraWorker()
        worker._startup_gate.qualified = True
        worker.wait = Mock(return_value=True)
        worker.requestInterruption = Mock()
        self.assertTrue(worker.stop(timeout_ms=25))
        self.assertTrue(worker._startup_gate.consumed)
        self.assertFalse(worker._startup_gate.qualified)

    def test_failed_face_scan_does_not_verify_a_new_candidate(self):
        current_regions = ((0.2, 0.1, 0.5, 0.65),)
        state = CameraWorker._updated_face_scan_state(
            current_regions,
            0.90,
            0.90,
            (),
            1.03,
            1.20,
            0.90,
            True,
            False,
        )
        self.assertEqual(state, (current_regions, 0.90, 0.90))

    def test_orientation_distinguishes_front_and_hand_specific_edges(self):
        points = [Landmark(0.0, 0.0, 0.0) for _ in range(21)]
        points[5] = Landmark(1.0, 0.0, 0.0)
        points[17] = Landmark(0.0, 1.0, 0.0)
        front = HandObservation("Right", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(front)[0], "PALM FRONT")

        points[5] = Landmark(0.0, 1.0, 0.0)
        points[17] = Landmark(0.0, 0.0, 1.0)
        right_edge = HandObservation("Right", tuple(points), tuple(points))
        left_edge = HandObservation("Left", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(right_edge)[0], "THUMB EDGE")
        self.assertEqual(CameraWorker._hand_orientation(left_edge)[0], "PINKY EDGE")

    def test_orientation_covers_diagonal_and_vertical_edge_states(self):
        points = [Landmark(0.0, 0.0, 0.0) for _ in range(21)]
        # Cross((0, 1, 0), (-.8, 0, .6)) gives the normalized
        # front-right normal (.6, 0, .8) for the right hand.
        points[5] = Landmark(0.0, 1.0, 0.0)
        points[17] = Landmark(-0.8, 0.0, 0.6)
        diagonal = HandObservation("Right", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(diagonal)[0], "FRONT-RIGHT EDGE")

        # Cross((1, 0, 0), (0, 0, 1)) points straight upward in image space.
        points[5] = Landmark(1.0, 0.0, 0.0)
        points[17] = Landmark(0.0, 0.0, 1.0)
        up = HandObservation("Left", tuple(points), tuple(points))
        self.assertEqual(CameraWorker._hand_orientation(up)[0], "UP EDGE")

    def test_handedness_is_preserved_when_swap_is_off(self):
        hands = CameraWorker._to_hands(fake_result("Right"), False)
        self.assertEqual(hands[0].handedness, "Right")

    def test_handedness_is_reversed_when_swap_is_on(self):
        hands = CameraWorker._to_hands(fake_result("Right"), True)
        self.assertEqual(hands[0].handedness, "Left")

    def test_duplicate_handedness_is_spatially_repaired_for_mirrored_preview(self):
        hands = CameraWorker._to_hands(duplicate_handedness_result(), False)
        self.assertEqual([hand.handedness for hand in hands], ["Right", "Left"])

    def test_startup_activation_requires_hold_then_both_release(self):
        gate = StartupActivationGate(hold_seconds=0.35)
        self.assertFalse(gate.update(True, True, True, 1.0)[0])
        self.assertFalse(gate.update(True, True, True, 1.2)[0])
        qualified = gate.update(True, True, True, 1.36)
        self.assertFalse(qualified[0])
        self.assertIn("Release both fists", qualified[1])
        self.assertFalse(gate.update(True, False, True, 1.4)[0])
        activated = gate.update(True, False, False, 1.45)
        self.assertTrue(activated[0])
        self.assertTrue(gate.consumed)

    def test_startup_activation_cannot_run_twice(self):
        gate = StartupActivationGate(hold_seconds=0.1)
        gate.update(True, True, True, 1.0)
        gate.update(True, True, True, 1.11)
        self.assertTrue(gate.update(True, False, False, 1.2)[0])
        self.assertFalse(gate.update(True, True, True, 2.0)[0])
        self.assertFalse(gate.update(True, False, False, 2.2)[0])

    def test_losing_a_hand_resets_startup_hold(self):
        gate = StartupActivationGate(hold_seconds=0.35)
        gate.update(True, True, True, 1.0)
        gate.update(False, False, False, 1.3)
        self.assertFalse(gate.update(True, True, True, 1.4)[0])
        self.assertFalse(gate.qualified)

    def test_manual_activation_consumes_startup_gesture(self):
        gate = StartupActivationGate()
        gate.consume()
        self.assertFalse(gate.update(True, True, True, 1.0)[0])
        self.assertTrue(gate.consumed)

    def test_resuming_control_centers_the_pointer(self):
        class Controller:
            def __init__(self):
                self.center_calls = 0

            def center_pointer(self):
                self.center_calls += 1

        worker = CameraWorker()
        controller = Controller()
        worker._controller = controller
        worker._dispatch((GestureAction("pause_changed", amount=1), GestureAction("pause_changed", amount=0)))
        self.assertEqual(controller.center_calls, 1)

    def test_app_switch_actions_use_the_platform_switch_seam(self):
        class Controller:
            def __init__(self):
                self.directions = []
                self.task_view_calls = 0
                self.desktop_calls = 0

            def switch_application(self, direction):
                self.directions.append(direction)

            def task_view(self):
                self.task_view_calls += 1

            def show_desktop(self):
                self.desktop_calls += 1

        worker = CameraWorker()
        controller = Controller()
        worker._controller = controller
        worker._dispatch((GestureAction("app_next"), GestureAction("app_previous"), GestureAction("task_view"), GestureAction("show_desktop")))
        self.assertEqual(controller.directions, [1, -1])
        self.assertEqual(controller.task_view_calls, 1)
        self.assertEqual(controller.desktop_calls, 1)

    def test_middle_click_dispatch_uses_controller_seam(self):
        class Controller:
            def __init__(self):
                self.calls = 0

            def middle_click(self):
                self.calls += 1

        worker = CameraWorker()
        controller = Controller()
        worker._controller = controller
        worker._dispatch((GestureAction("middle_click"),))
        self.assertEqual(controller.calls, 1)

    def test_slow_adjustable_hit_test_is_opt_in(self):
        class Controller:
            def __init__(self):
                self.begin_calls = 0
                self.cancel_calls = 0

            def begin_context_pinch(self):
                self.begin_calls += 1

            def cancel_context_pinch(self):
                self.cancel_calls += 1

        worker = CameraWorker()
        controller = Controller()
        worker._controller = controller
        worker._dispatch((GestureAction("pinch_start"),))
        self.assertEqual(controller.begin_calls, 0)
        self.assertEqual(controller.cancel_calls, 1)
        worker.set_tuning({"adjustable_control_detection": 1})
        worker._dispatch((GestureAction("pinch_start"),))
        self.assertEqual(controller.begin_calls, 1)

if __name__ == "__main__":
    unittest.main()
