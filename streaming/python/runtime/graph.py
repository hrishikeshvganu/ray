import enum

import ray
import ray.streaming.generated.remote_call_pb2 as remote_call_pb
import ray.streaming.operator as operator
import ray.streaming.partition as partition
from ray.streaming.generated.streaming_pb2 import Language


class NodeType(enum.Enum):
    """
    SOURCE: Sources are where your program reads its input from

    TRANSFORM: Operators transform one or more DataStreams into a new
     DataStream. Programs can combine multiple transformations into
     sophisticated dataflow topologies.

    SINK: Sinks consume DataStreams and forward them to files, sockets,
     external systems, or print them.
    """
    SOURCE = 0
    TRANSFORM = 1
    SINK = 2


class ExecutionEdge:
    def __init__(self, edge_pb, language):
        self.source_execution_vertex_id = edge_pb.source_execution_vertex_id
        self.target_execution_vertex_id = edge_pb.target_execution_vertex_id
        partition_bytes = edge_pb.partition
        # Sink node doesn't have partition function,
        # so we only deserialize partition_bytes when it's not None or empty
        if language == Language.PYTHON and partition_bytes:
            self.partition = partition.load_partition(partition_bytes)


class ExecutionVertex:
    def __init__(self, vertex_pb):
        self.execution_vertex_id = vertex_pb.execution_vertex_id
        self.execution_job_vertex_Id = vertex_pb.execution_job_vertex_Id
        self.execution_job_vertex_name = vertex_pb.execution_job_vertex_name
        self.execution_vertex_index = vertex_pb.execution_vertex_index
        self.parallelism = vertex_pb.parallelism
        if vertex_pb.language == Language.PYTHON:
            operator_bytes = vertex_pb.operator  # python operator descriptor
            self.stream_operator = operator.load_operator(operator_bytes)
        self.worker_actor = ray.actor.ActorHandle. \
            _deserialization_helper(vertex_pb.worker_actor)
        self.container_id = vertex_pb.container_id
        self.build_time = vertex_pb.build_time
        self.language = vertex_pb.language
        self.config = vertex_pb.config
        self.resource = vertex_pb.resource


class ExecutionVertexContext:
    def __init__(self,
                 vertex_context_pb: remote_call_pb.ExecutionVertexContext):
        self.execution_vertex = \
            ExecutionVertex(vertex_context_pb.current_execution_vertex)
        self.upstream_execution_vertices = [
            ExecutionVertex(vertex)
            for vertex in vertex_context_pb.upstream_execution_vertices
        ]
        self.downstream_execution_vertices = [
            ExecutionVertex(vertex)
            for vertex in vertex_context_pb.downstream_execution_vertices
        ]
        self.input_execution_edges = [
            ExecutionEdge(edge, self.execution_vertex.language)
            for edge in vertex_context_pb.input_execution_edges
        ]
        self.output_execution_edges = [
            ExecutionEdge(edge, self.execution_vertex.language)
            for edge in vertex_context_pb.output_execution_edges
        ]

    def get_parallelism(self):
        return self.execution_vertex.parallelism

    def get_upstream_parallelism(self):
        if self.upstream_execution_vertices:
            return self.upstream_execution_vertices[0].parallelism
        return 0

    def get_downstream_parallelism(self):
        if self.downstream_execution_vertices:
            return self.downstream_execution_vertices[0].parallelism
        return 0

    @property
    def build_time(self):
        return self.execution_vertex.build_time

    @property
    def stream_operator(self):
        return self.execution_vertex.stream_operator

    @property
    def config(self):
        return self.execution_vertex.config

    def get_task_id(self):
        return self.execution_vertex.execution_vertex_id

    def get_source_actor_by_vertex_id(self, execution_vertex_id):
        for vertex in self.upstream_execution_vertices:
            if vertex.execution_vertex_id == execution_vertex_id:
                return vertex.worker_actor
        raise Exception("ExecutionVertex %s does not exist!"
                        .format(execution_vertex_id))

    def get_target_actor_by_vertex_id(self, execution_vertex_id):
        for vertex in self.downstream_execution_vertices:
            if vertex.execution_vertex_id == execution_vertex_id:
                return vertex.worker_actor
        raise Exception("ExecutionVertex %s does not exist!"
                        .format(execution_vertex_id))
