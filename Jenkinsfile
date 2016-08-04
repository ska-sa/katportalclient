node('docker') {
    docker.image('cambuilder:latest').inside('-u root') {

        stage 'Checkout SCM'
        checkout scm

        stage 'Install & Unit Tests'
        timeout(time: 180, unit: 'MINUTES') {
            sh 'pip install . -U --pre --user'
            sh 'python setup.py nosetests -v --with-xunit --with-xcoverage --xcoverage-file=coverage.xml --cover-package=katportalclient --cover-inclusive'
            step([$class: 'JUnitResultArchiver', testResults: 'nosetests.xml'])
        }

        stage 'Build & Upload'
        sh 'fpm -s python -t deb . # --python-bin="/usr/bin/python2.7" .'
        echo '!!!!!!TODO: UPLOAD .DEB!!!!!!!'
        sh 'python setup.py bdist_wheel'
        sh 'devpi use http://pypi.camlab.kat.ac.za/pypi/trusty'
        sh 'devpi login pypi --password='
        sh 'devpi upload dist/*.whl'

        archive '*.whl,*.deb'
    }
}
