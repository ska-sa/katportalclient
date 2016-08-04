node('docker') {
    docker.image('cambuilder:latest').inside('-u root') {
        try {
            stage 'Checkout SCM'
            checkout scm

            stage 'Install & Unit Tests'
            timeout(time: 30, unit: 'MINUTES') {
                sh 'pip install . -U --pre'
                sh 'python setup.py nosetests -v --with-xunit'
                step([$class: 'JUnitResultArchiver', testResults: 'nosetests.xml'])
            }

            stage 'Build .whl & .deb'
            sh 'fpm -s python -t deb .'
            sh 'python setup.py bdist_wheel'
            sh 'mv *.deb dist/'

            stage 'Upload .whl & .deb'
            sshagent(['88805e11-10f8-4cc2-b6b8-cba2268ceb2c']) {
                sh "scp -o StrictHostKeyChecking=no dist/*.deb kat@apt.camlab.kat.ac.za:/var/www/apt/ubuntu/dists/trusty/main/binary-amd64/katportalclient/"
                sh "ssh -o StrictHostKeyChecking=no kat@apt.camlab.kat.ac.za '/var/www/apt/ubuntu/scripts/update_repo.sh'"
            }

            sh 'devpi use http://pypi.camlab.kat.ac.za/pypi/trusty'
            sh 'devpi login pypi --password='
            sh 'devpi upload dist/*.whl'
        } finally {
            stage 'Cleanup workspace'
            deleteDir()
        }
    }
}
