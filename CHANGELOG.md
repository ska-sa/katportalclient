13th Sep 2019 (0.2.1)
* Fixes a bug where incorrect sensor info is returned from `sensor_detail` and does not match the documentation.

11th Sep 2019 (0.2.0)
 * changes to internal API 
   * Changed `SensorSampleValueTs` to `SensorSampleValueTime`
   * `timestamp` has been changed to `sample_time`
   * `value_timestamp` has been changed to `value_time`
 * Removal of namespaces when retrieving historical data.
 * Changed url endpoint for historical data. 
 * Updated katportalclient `examples` to align with changes.
 * Removed timeout argument from `get_sensor_history.py` examples.
 * Changes to `sensor_detail`, `sensor_history`, `sensor_names`
 
30 Aug 2019 (0.1.1)
 * Changed COPYING to LICENSE.
 * Added `long_description` to setup.py.
 * Updated copyright header.

27 Aug 2019 (0.1.0)
 * Start of CHANGELOG in preparation for 0.1.0 release.