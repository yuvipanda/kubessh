import pytest
from kubessh.pod import UserPod

def test_pod_name():
    """
    Pod's Name is properly expanded with templates / escaping
    """
    assert UserPod('test-name', 'default').pod_name == 'ssh-test-2dname'

