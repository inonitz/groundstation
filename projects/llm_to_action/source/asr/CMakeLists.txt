# ---------------------------------------------------------------------------
# ASR (speech-to-text) server node.
# ---------------------------------------------------------------------------
set(ASR_SERVER_NODE_NAME_POSTFIX asr_server)
set(ASR_SERVER_NODE_SOURCES
    asr_node_base.hpp
    asr_node.hpp
    asr_node.cpp
)

define_ros2_node(${ASR_SERVER_NODE_NAME_POSTFIX} "${ASR_SERVER_NODE_SOURCES}")
ros2_node_add_library(${ASR_SERVER_NODE_NAME_POSTFIX}
    STTSERVER::SpeechToTextServer
    util_base_header
)
