import setuptools

setuptools.setup(
    name="kubessh",
    version='0.1',
    url="https://github.com/yuvipanda/kubessh",
    author="Yuvi Panda",
    author_email="yuvipanda@gmail.com",
    license="Apache-2",
    description="SSH server to spawn users into kubernetes pods",
    packages=setuptools.find_packages(),
    install_requires=[
        'kubernetes',
        'asyncssh',
        'ptyprocess',
        'aiohttp',
        'traitlets',
        'escapism',
        'ruamel.yaml',
        'simpervisor'
    ],
    entry_points = {
        'console_scripts': [
            'kubessh=kubessh.app:main'
        ]
    }
)