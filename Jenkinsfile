pipeline {

    agent {
        label 'cambuilder'
    }

    stages {
        stage('Checkout SCM') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: "refs/heads/${env.BRANCH_NAME}"]],
                    extensions: [[$class: 'LocalBranch']],
                    userRemoteConfigs: scm.userRemoteConfigs,
                    doGenerateSubmoduleConfigurations: false,
                    submoduleCfg: []
                ])
            }
        }

        stage('Install & Unit Tests') {
            options {
                timestamps()
                timeout(time: 30, unit: 'MINUTES')
            }

            parallel {
                stage('py27') {
                    steps {
                        echo "Running nosetests on Python 2.7"
                        sh 'tox -e py27'
                    }
                }

                stage('py36') {
                    steps {
                        echo "Running nosetests on Python 3.6"
                        sh 'tox -e py36'
                    }
                }
            }

            post {
                always {
                    junit '*.xml'
                    archiveArtifacts '*.xml'
                }
            }
        }

        stage('Build .whl & .deb') {
            steps {
                sh 'fpm -s python -t deb .'
                sh 'python setup.py bdist_wheel'
                sh 'mv *.deb dist/'
            }
        }

        stage('Archive build artifact: .whl & .deb') {
            steps {
                archiveArtifacts 'dist/*'
            }
        }

        stage('Trigger downstream publish') {
            steps {
                build(job: 'publish-local', parameters: [
                    string(name: 'artifact_source', value: "${currentBuild.absoluteUrl}/artifact/dist/*zip*/dist.zip"),
                    string(name: 'source_branch', value: "${env.BRANCH_NAME}")])
            }
        }
    }
}
