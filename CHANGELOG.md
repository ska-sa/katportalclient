# Changelog

## [v0.2.2](https://github.com/ska-sa/katportalclient/tree/v0.2.2) (2020-04-30)

[Full Changelog](https://github.com/ska-sa/katportalclient/compare/v0.2.1...v0.2.2)

**Merged pull requests:**

- Generate documentation as part of CI build. [\#61](https://github.com/ska-sa/katportalclient/pull/61) ([mmphego](https://github.com/mmphego))
- Install latest ujson to fix float truncation [\#59](https://github.com/ska-sa/katportalclient/pull/59) ([lanceWilliams](https://github.com/lanceWilliams))
- Changed build agent from Ubuntu Trusty to Bionic [\#58](https://github.com/ska-sa/katportalclient/pull/58) ([mmphego](https://github.com/mmphego))
- Automate code linting and reject PR if fails. [\#57](https://github.com/ska-sa/katportalclient/pull/57) ([mmphego](https://github.com/mmphego))

## [v0.2.1](https://github.com/ska-sa/katportalclient/tree/v0.2.1) (2019-09-13)

[Full Changelog](https://github.com/ska-sa/katportalclient/compare/v0.2.0...v0.2.1)

**Merged pull requests:**

- fix sensor detail method [\#56](https://github.com/ska-sa/katportalclient/pull/56) ([tockards](https://github.com/tockards))

## [v0.2.0](https://github.com/ska-sa/katportalclient/tree/v0.2.0) (2019-09-11)

[Full Changelog](https://github.com/ska-sa/katportalclient/compare/v0.1.1...v0.2.0)

**Merged pull requests:**

- Fix quoting of sensor filters in URLs [\#53](https://github.com/ska-sa/katportalclient/pull/53) ([bmerry](https://github.com/bmerry))
- correct url for katstore [\#51](https://github.com/ska-sa/katportalclient/pull/51) ([tockards](https://github.com/tockards))
- Address PR Comments \#31 [\#47](https://github.com/ska-sa/katportalclient/pull/47) ([tockards](https://github.com/tockards))
- Merge master into new-katstore-integration feature [\#46](https://github.com/ska-sa/katportalclient/pull/46) ([tockards](https://github.com/tockards))
- MT-409: Test katportalclient against katstore64 [\#37](https://github.com/ska-sa/katportalclient/pull/37) ([xinyuwu](https://github.com/xinyuwu))
- Update katstore feature branch with master [\#36](https://github.com/ska-sa/katportalclient/pull/36) ([ajoubertza](https://github.com/ajoubertza))
- Feature/new katstore integration [\#31](https://github.com/ska-sa/katportalclient/pull/31) ([tockards](https://github.com/tockards))

## [v0.1.1](https://github.com/ska-sa/katportalclient/tree/v0.1.1) (2019-08-30)

[Full Changelog](https://github.com/ska-sa/katportalclient/compare/v0.1.0...v0.1.1)

**Merged pull requests:**

- add license and long\_description to setup.py [\#50](https://github.com/ska-sa/katportalclient/pull/50) ([tockards](https://github.com/tockards))

## [v0.1.0](https://github.com/ska-sa/katportalclient/tree/v0.1.0) (2019-08-29)

[Full Changelog](https://github.com/ska-sa/katportalclient/compare/98c0d8fea2ffdb32e9fbf96e1de57653e98cd3a5...v0.1.0)

**Closed issues:**

- Mixed messages on code reuse [\#28](https://github.com/ska-sa/katportalclient/issues/28)

**Merged pull requests:**

- add initial changelog [\#48](https://github.com/ska-sa/katportalclient/pull/48) ([tockards](https://github.com/tockards))
- Make katportalclient work on newer versions of Tornado [\#45](https://github.com/ska-sa/katportalclient/pull/45) ([bmerry](https://github.com/bmerry))
- Capture block ID usage in examples [\#44](https://github.com/ska-sa/katportalclient/pull/44) ([bngcebetsha](https://github.com/bngcebetsha))
- Request a list of sb\_ids associated with a given capture block ID [\#43](https://github.com/ska-sa/katportalclient/pull/43) ([bngcebetsha](https://github.com/bngcebetsha))
- Trigger downstream publish [\#42](https://github.com/ska-sa/katportalclient/pull/42) ([sw00](https://github.com/sw00))
- Doc strings updated [\#41](https://github.com/ska-sa/katportalclient/pull/41) ([rohanschwartz](https://github.com/rohanschwartz))
- Add multiple sensor readings request [\#40](https://github.com/ska-sa/katportalclient/pull/40) ([lanceWilliams](https://github.com/lanceWilliams))
- Add Python 3 compatibility [\#38](https://github.com/ska-sa/katportalclient/pull/38) ([ajoubertza](https://github.com/ajoubertza))
- Increase HTTP request timeout to 60 seconds [\#35](https://github.com/ska-sa/katportalclient/pull/35) ([ajoubertza](https://github.com/ajoubertza))
- Add `sensor\_value` function that returns latest sensor reading [\#34](https://github.com/ska-sa/katportalclient/pull/34) ([SKAJohanVenter](https://github.com/SKAJohanVenter))
- Revert new katstore changes on master [\#32](https://github.com/ska-sa/katportalclient/pull/32) ([ajoubertza](https://github.com/ajoubertza))
- User/bulelani/cb 1824/add test for subarray sensor lookup [\#30](https://github.com/ska-sa/katportalclient/pull/30) ([bxaia](https://github.com/bxaia))
- Update license details to BSD [\#29](https://github.com/ska-sa/katportalclient/pull/29) ([ajoubertza](https://github.com/ajoubertza))
- Allow sensor subarray lookup for component names [\#27](https://github.com/ska-sa/katportalclient/pull/27) ([ajoubertza](https://github.com/ajoubertza))
- added a sensor\_subarray\_lookup method that calls a katportal endpoint… [\#26](https://github.com/ska-sa/katportalclient/pull/26) ([bxaia](https://github.com/bxaia))
- Fix sensor\_detail request if duplicates found [\#25](https://github.com/ska-sa/katportalclient/pull/25) ([ajoubertza](https://github.com/ajoubertza))
- Improved usage of katpoint for better clarity [\#24](https://github.com/ska-sa/katportalclient/pull/24) ([fjoubert](https://github.com/fjoubert))
- added example usage of the katpoint target and antenna objects [\#23](https://github.com/ska-sa/katportalclient/pull/23) ([fjoubert](https://github.com/fjoubert))
- Added auth, userlogs, removed future targets details and many unit tests [\#22](https://github.com/ska-sa/katportalclient/pull/22) ([fjoubert](https://github.com/fjoubert))
- Reconnection logic + resending jsonrpc requests on reconnect [\#21](https://github.com/ska-sa/katportalclient/pull/21) ([fjoubert](https://github.com/fjoubert))
- Improve basic websocket subscription example [\#20](https://github.com/ska-sa/katportalclient/pull/20) ([ajoubertza](https://github.com/ajoubertza))
- Methods and example of how to get schedule block targets and target details from our catalogues [\#19](https://github.com/ska-sa/katportalclient/pull/19) ([fjoubert](https://github.com/fjoubert))
- User/lize/cb 1498 fix retrieve sensor data [\#18](https://github.com/ska-sa/katportalclient/pull/18) ([lvdheever](https://github.com/lvdheever))
- User/lize/cb 1498 [\#17](https://github.com/ska-sa/katportalclient/pull/17) ([lvdheever](https://github.com/lvdheever))
- Allow simultaneous sensor history requests [\#16](https://github.com/ska-sa/katportalclient/pull/16) ([ajoubertza](https://github.com/ajoubertza))
- Allow historical sensor queries [\#15](https://github.com/ska-sa/katportalclient/pull/15) ([ajoubertza](https://github.com/ajoubertza))
- Add sensor list and sensor detail functions [\#14](https://github.com/ska-sa/katportalclient/pull/14) ([ajoubertza](https://github.com/ajoubertza))
- jenkinsfile tweaks to always checkout the correct head of the branch;… [\#13](https://github.com/ska-sa/katportalclient/pull/13) ([fjoubert](https://github.com/fjoubert))
- Methods to get schedule block info [\#12](https://github.com/ska-sa/katportalclient/pull/12) ([ajoubertza](https://github.com/ajoubertza))
- Request sitemap from portal webserver on initialisation [\#11](https://github.com/ska-sa/katportalclient/pull/11) ([ajoubertza](https://github.com/ajoubertza))
- Flake8, docstring and copyright fixes [\#10](https://github.com/ska-sa/katportalclient/pull/10) ([ajoubertza](https://github.com/ajoubertza))
- improved debug logging call [\#9](https://github.com/ska-sa/katportalclient/pull/9) ([fjoubert](https://github.com/fjoubert))
- better local branch checkout in Jenkinsfile [\#8](https://github.com/ska-sa/katportalclient/pull/8) ([fjoubert](https://github.com/fjoubert))
- Indentation fix [\#7](https://github.com/ska-sa/katportalclient/pull/7) ([bxaia](https://github.com/bxaia))
- User/bulelani/jenkinsfile archive artifacts [\#6](https://github.com/ska-sa/katportalclient/pull/6) ([fjoubert](https://github.com/fjoubert))
- Jenkinsfile & local version [\#5](https://github.com/ska-sa/katportalclient/pull/5) ([fjoubert](https://github.com/fjoubert))
