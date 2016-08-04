docker.image('camnode:latest').inside {
    sh 'echo in master node'
    sh 'pwd && ifconfig && whoami'
    checkout scm
    sh 'sudo pip install /home/kat/katportalclient -U --pre'
    sh 'python /home/kat/katportalclient/setup.py nosetests -v --with-xunit --with-xcoverage --xcoverage-file=coverage.xml --cover-package=katportalclient --cover-inclusive'
}
