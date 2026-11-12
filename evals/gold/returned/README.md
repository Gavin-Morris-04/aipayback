# Nick's returned label files

Put the label files Nick sends back here, keeping his file names:

- the passage packets (`AMZN_packet_v1.xlsx`, `BLK_packet_v1.xlsx`, ...), then run `uv run aipb import-labels`
- the status packet (`status_packet_v1.xlsx`), then run `uv run aipb import-statuses`

Then `uv run aipb eval` (passages) or `uv run aipb eval-status` (statuses). All of these cost $0.

Commit the .xlsx files together with the gold CSVs they produce, so every eval number can be traced to Nick's file.
