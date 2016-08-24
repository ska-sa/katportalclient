node('docker') {
    stage 'Cleanup workspace'
    dir('dist') {
        deleteDir()
    }

    docker.image('cambuilder:latest').inside('-u root') {
        stage 'Checkout SCM'
            checkout scm
            sh "git checkout ${env.BRANCH_NAME}"

        stage 'Install & Unit Tests'
            timeout(time: 30, unit: 'MINUTES') {
            sh 'pip install . -U --pre --user'
            sh 'python setup.py nosetests -v --with-xunit'
            step([$class: 'JUnitResultArchiver', testResults: 'nosetests.xml'])
        }

        stage 'Build .whl & .deb'
            sh 'fpm -s python -t deb .'
            sh 'python setup.py bdist_wheel'
            sh 'mv *.deb dist/'
            sh 'chmod 777 -R dist/'

        stage 'Archive build artifact: .whl & .deb'
            step([$class: 'ArtifactArchiver', artifacts: '*.whl,*.deb', fingerprint: true])
    }
}
