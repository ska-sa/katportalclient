node('docker') {
    docker.image('camslave:latest').inside('-u root') {

        stage 'Checkout SCM'
        checkout scm

        stage 'Unit Tests'
        sh 'pip install . -U --pre --user'
        sh 'python setup.py nosetests -v --with-xunit --with-xcoverage --xcoverage-file=coverage.xml --cover-package=katportalclient --cover-inclusive'

        stage 'Build and Upload'
        sh 'echo "fpm and wheels build here please!!"'
    }
}
