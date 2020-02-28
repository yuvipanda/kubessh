import asyncssh
import asyncio
import subprocess
from traitlets.config import LoggingConfigurable
from simpervisor import SupervisedProcess
import socket
from kubessh.shell import UserPod, ShellState

def random_port():
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

# FIXME: Split this into two classes, at least.
class BaseServer(asyncssh.SSHServer, LoggingConfigurable):
    def connection_made(self, conn):
        self.conn = conn

    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        # Only allow localhost connections
        if dest_host != '127.0.0.1':
            raise asyncssh.ChannelOpenError(
                asyncssh.OPEN_ADMINISTRATIVELY_PROHIBITED,
                "Only localhost connections allowed"
            )

        username = self.conn.get_extra_info('username')
        # FIXME: namespace
        user_pod = UserPod(username, 'default')
        port = random_port()
        command = [
            'kubectl',
            'port-forward',
            user_pod.pod_name,
            f'{port}:{dest_port}'
        ]
        print(' '.join(command))
        async def _socket_ready(proc):
            try:
                sock = socket.create_connection(('127.0.0.1', port))
                sock.close()
                return True
            except:
                # FIXME: Be more specific in errors we are catching?
                return False

        # FIXME: Reap this
        proc = SupervisedProcess(
            'kubectl', *command,
            always_restart=True,
            ready_func=_socket_ready
        )
        async def transfer_data(reader, writer):
            # Make sure our pod is running
            async for status in user_pod.ensure_running():
                if status == ShellState.RUNNING:
                    break
            # Make sure our kubectl port-forward is running
            await proc.start()
            await proc.ready()

            # Connect to the local end of the kubectl port-forward
            (upstream_reader, upstream_writer) = await asyncio.open_connection('127.0.0.1', port)

            # FIXME: This should be as fully bidirectional as possible, with minimal buffering / timeouts
            while not reader.at_eof():
                try:
                    data = await asyncio.wait_for(reader.read(8092), timeout=0.1)
                except asyncio.TimeoutError:
                    data = None
                if data:
                    upstream_writer.write(data)
                    await upstream_writer.drain()

                try:
                    in_data = await asyncio.wait_for(upstream_reader.read(8092), timeout=0.1)
                except asyncio.TimeoutError:
                    in_data = None
                if in_data:
                    writer.write(in_data)
                    await writer.drain()
                if upstream_reader.at_eof():
                    break
            writer.close()

        return transfer_data

class Authenticator(BaseServer):
    """
    Base class for Authentication plugins for KubeSSH.

    Should override the authentication specific methods of
    asyncssh.SSHServer
    """
    pass