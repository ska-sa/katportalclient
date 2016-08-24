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
            sh 'chmod 777 -R dist'

        stage 'Archive build artifact: .whl & .deb'
            archive 'dist/*.whl,dist/*.deb'

        stage 'Trigger downstream publish'
            ARTIFACT_SOURCE = "${env.JENKINS_HOME}/jobs/${env.JOB_NAME}/branches/${env.BRANCH_NAME}/builds/${env.BUILD_ID}/archive/dist"
            echo ARTIFACT_SOURCE
            build job: 'publish-local-whl', parameters: [[$class: 'StringParameterValue', name: 'artifact_source', value: ARTIFACT_SOURCE.toString()],[$class: 'StringParameterValue', name: 'source_branch', value: {$env.BRANCH_NAME}]], wait: false
    }
}
