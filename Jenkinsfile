node('camnode') { //the label of the docker image on jenkins
    stage 'Build and Test'
    docker.image('camnode').inside { //the name of the actual docker image
        checkout scm
        sh 'sudo pip install /home/kat/katportalclient -U --pre'
        sh 'python /home/kat/katportalclient/setup.py nosetests -v --with-xunit --with-xcoverage --xcoverage-file=coverage.xml --cover-package=katportalclient --cover-inclusive'
    }
}
