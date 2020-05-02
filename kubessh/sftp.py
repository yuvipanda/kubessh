import sys
import os
import asyncssh.sftp
import subprocess
from kubessh.pod import UserPod
from traitlets import Unicode
from traitlets.config import LoggingConfigurable

class DelegateSFTPServerHandler(asyncssh.sftp.SFTPServerHandler):
    """An SFTP server session handler that delegates all SFTP-related
    communication to a subprocess.
    """
    def __init__(self, server, reader, writer):
        super().__init__(server, reader, writer)
        self.username = server.channel.get_extra_info('username')
        self._init_delegate()
        self.logger.info(f"Initialized {self.__class__} for {self.username}")

    def _init_delegate(self):
        self._proc = subprocess.Popen(
            ['./sftp-server'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr
        )
        self._proc_stdin = self._proc.stdin
        self._proc_stdout = self._proc.stdout

    async def _cleanup(self, exc):
        self._proc.terminate()
        await super()._cleanup(exc)

    async def _forward_incoming_packet_to_delegate(self, data):
        self.logger.debug1(f'write {len(data)} byte packet to delegate process')
        self.logger.debug2(f'{data}')
        self._proc_stdin.write(
            len(data).to_bytes(length=4, byteorder='big', signed=False))
        self._proc_stdin.write(data)
        self._proc_stdin.flush()

    async def _read_packet_from_delegate(self):
        self.logger.debug1('read packet from delegate process')
        ch = self._proc_stdout
        self.logger.debug2('read packet length field')
        pkt_len = int.from_bytes(ch.peek()[:4], byteorder='big', signed=False)
        self.logger.debug2(f'attempt to read {pkt_len} byte packet')
        packet = ch.read(pkt_len + 4)
        self.logger.debug2(f'delegate packet is {packet}')
        return packet

    async def _forward_outgoing_packet_from_delegate(self, data):
        self._writer.write(data)

    async def _process_packet(self, pkttype, pktid, packet):
        self.log_received_packet(pkttype, pktid, packet, note='forwarded to subprocess')
        await self._forward_incoming_packet_to_delegate(packet.get_full_payload())
        response = await self._read_packet_from_delegate()
        # TODO: (would have to redundantly decode packet to log it, omitted for now)
        #self.log_sent_packet(pkttype, pktid, packet, note='forwarded from subprocess')
        await self._forward_outgoing_packet_from_delegate(response)

    async def run(self):
        # skip super's SFTP init handling, the subprocess does this here
        await self.recv_packets()


class KubeSFTPServerHandler(DelegateSFTPServerHandler, LoggingConfigurable):

    # where the SFTP binary lives in the KubeSSH server image
    sftp_binary_source_path = Unicode(
        '/usr/local/share/kubessh/sftp-server',
        allow_none=False,
        help="""
        Path in the KubeSSH server container to the static sftp-server binary.
        """,
        config=True
    )

    # where the SFTP binary goes in the user pod
    sftp_binary_upload_path = Unicode(
        '.local/sbin/kubessh-sftp-server',
        allow_none=False,
        help="""
        Path inside the user pod where the sftp-server binary will be uploaded.

        Must be full path including the executable name, and can be absolute or
        relative to the working dir. Must be writable by the user the pod runs
        as.
        """,
        config=True
    )

    def __init__(self, server, reader, writer):
        from kubessh.app import app
        super(LoggingConfigurable, self).__init__(parent=app)
        super().__init__(server, reader, writer)

    def _run_setup_command(self, *kubectl_command):
        self.logger.info(f'executing: {kubectl_command}')
        cmd = subprocess.Popen(kubectl_command)
        return cmd.wait()

    def _init_delegate(self):
        self.namespace = self.parent.default_namespace
        self.pod_name = UserPod(
            parent=self.parent, namespace=self.namespace,
            username=self.username).pod_name
        # ensure sftp-server binary is copied into the user pod
        self._run_setup_command(
            'kubectl',
            '--namespace', self.namespace,
            'exec',
            '-c', 'shell',
            self.pod_name,
            '--', 'mkdir', '-p',
            os.path.dirname(self.sftp_binary_upload_path))
        self._run_setup_command(
            'kubectl', 'cp',
            self.sftp_binary_source_path,
            f'{self.namespace}/{self.pod_name}:{self.sftp_binary_upload_path}',
            '-c', 'shell')
        self._run_setup_command(
            'kubectl',
            '--namespace', self.namespace,
            'exec',
            '-c', 'shell',
            self.pod_name,
            '--', 'chmod', '+x', self.sftp_binary_upload_path)

        # start sftp-server binary and redirect stdin/stdout
        kubectl_command = [
            'kubectl',
            '--namespace', self.namespace,
            'exec',
            '-c', 'shell',
            '--stdin',
            self.pod_name,
            '--', self.sftp_binary_upload_path
        ]
        self.logger.info(f'starting delegate sftp-server process: {kubectl_command}')

        self._proc = subprocess.Popen(
            kubectl_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr
        )
        self._proc_stdin = self._proc.stdin
        self._proc_stdout = self._proc.stdout



## XXX: as of asyncssh v2.2.1, there appears to be no proper way to override
## the default SFTPServerHandler implementation. The below monkey-patching
## works for now, but should be replaced once there is a better way to do this.

import asyncssh.stream
import asyncssh.sftp

def run_override(sftp_server, reader, writer):
    return KubeSFTPServerHandler(sftp_server, reader, writer).run()

asyncssh.sftp.run_sftp_server = run_override
asyncssh.stream.run_sftp_server = run_override
