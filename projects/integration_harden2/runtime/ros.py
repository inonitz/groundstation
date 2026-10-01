"""The ROS2 context: ONE for the whole app. Started before the first ROS2 node (speech
in, the keys, the ROS video), stopped after the last one closes.

rclpy's own Ctrl+C handler is OFF: it would shut the context down under a spinning
executor and throw into our threads. Our nodes stop in the one order that needs no
exception handling: executor.shutdown(), join the spin thread, destroy the node."""
import threading

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions


def start():
    """Start the context once; a second call does nothing."""
    if not rclpy.ok():
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    return


def stop():
    """Stop the context after every node has closed."""
    if rclpy.ok():
        rclpy.shutdown()
    return


class Subscription:
    """One ROS2 topic subscription on its OWN node and its OWN executor thread (never the
    global executor: nodes do not share one). The one home for this pattern: the keys,
    speech in and the ROS video all use it.
    @callback(msg) runs on the executor thread."""

    def __init__(self, node_name, msg_type, topic, callback):
        start()
        self._node = rclpy.create_node(node_name)
        self._node.create_subscription(msg_type, topic, callback, 10)

        self._exec = SingleThreadedExecutor()
        self._exec.add_node(self._node)
        self._spin = threading.Thread(
            target=self._exec.spin,
            name=node_name,
            daemon=True
        )
        self._spin.start()
        return

    def close(self):
        """Stop in the order that needs no exception handling: executor, thread, node."""
        self._exec.shutdown()
        self._spin.join()
        self._node.destroy_node()
        return
