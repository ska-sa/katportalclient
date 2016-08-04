node('docker') {
    docker.image('camslave:latest').inside {

        stage 'Checkout SCM'
        checkout scm

        stage 'Unit Tests'
        sh 'sudo pip install . -U --pre'
        sh 'python setup.py nosetests -v --with-xunit --with-xcoverage --xcoverage-file=coverage.xml --cover-package=katportalclient --cover-inclusive'
    }
}
