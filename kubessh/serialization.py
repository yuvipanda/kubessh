"""
Convenience functions for creating pod templates.
"""
from collections import namedtuple
import copy
from kubernetes import client
import json

try:
    import yaml
except ImportError:
    yaml = False

# FIXME: ApiClient provides us serialize / deserialize methods,
# but unfortunately also starts a threadpool for no reason! This
# takes up resources, so we try to not make too many.
SERIALIZATION_API_CLIENT = client.ApiClient()


def _set_k8s_attribute(obj, attribute, value):
    """
    Set a specific value on a kubernetes object's attribute

    obj
        an object from Kubernetes Python API client
    attribute
        Should be a Kubernetes API style attribute (with camelCase)
    value
        Can be anything (string, list, dict, k8s objects) that can be
        accepted by the k8s python client
    """
    current_value = None
    attribute_name = None
    # All k8s python client objects have an 'attribute_map' property
    # which has as keys python style attribute names (api_client)
    # and as values the kubernetes JSON API style attribute names
    # (apiClient). We want to allow users to use the JSON API style attribute
    # names only.
    for python_attribute, json_attribute in obj.attribute_map.items():
        if json_attribute == attribute:
            attribute_name = python_attribute
            break
    else:
        raise ValueError('Attribute must be one of {}'.format(obj.attribute_map.values()))

    if hasattr(obj, attribute_name):
        current_value = getattr(obj, attribute_name)

    if current_value is not None:
        # This will ensure that current_value is something JSONable,
        # so a dict, list, or scalar
        current_value = SERIALIZATION_API_CLIENT.sanitize_for_serialization(
            current_value
        )

    if isinstance(current_value, dict):
        # Deep merge our dictionaries!
        setattr(obj, attribute_name, merge_dictionaries(current_value, value))
    elif isinstance(current_value, list):
        # Just append lists
        setattr(obj, attribute_name, current_value + value)
    else:
        # Replace everything else
        setattr(obj, attribute_name, value)


def merge_dictionaries(a, b, path=None, update=True):
    """
    Merge two dictionaries recursively.

    From https://stackoverflow.com/a/25270947
    """
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dictionaries(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass # same leaf value
            elif isinstance(a[key], list) and isinstance(b[key], list):
                for idx, val in enumerate(b[key]):
                    a[key][idx] = merge_dictionaries(a[key][idx],
                                                     b[key][idx],
                                                     path + [str(key), str(idx)],
                                                     update=update)
            elif update:
                a[key] = b[key]
            else:
                raise Exception('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            a[key] = b[key]
    return a

_FakeResponse = namedtuple('_FakeResponse', ['data'])

def make_api_object_from_dict(dict_, kind=client.V1Pod):
    # FIXME: We can't use the 'deserialize' function since
    # that expects a response object!
    return SERIALIZATION_API_CLIENT.deserialize(
        _FakeResponse(data=json.dumps(dict_)),
        kind
    )


def clean_pod_template(pod_template):
    """ Normalize pod template and check for type errors """
    if isinstance(pod_template, str):
        msg = ('Expected a kubernetes.client.V1Pod object, got %s'
               'If trying to pass a yaml filename then use '
               'KubeCluster.from_yaml')
        raise TypeError(msg % pod_template)

    if isinstance(pod_template, dict):
        msg = ('Expected a kubernetes.client.V1Pod object, got %s'
               'If trying to pass a dictionary specification then use '
               'KubeCluster.from_dict')
        raise TypeError(msg % str(pod_template))

    pod_template = copy.deepcopy(pod_template)

    # Make sure metadata / labels / env objects exist, so they can be modified
    # later without a lot of `is None` checks
    if pod_template.metadata is None:
        pod_template.metadata = client.V1ObjectMeta()
    if pod_template.metadata.labels is None:
        pod_template.metadata.labels = {}

    if pod_template.spec.containers[0].env is None:
        pod_template.spec.containers[0].env = []

    return pod_template
