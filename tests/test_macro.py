"""RBI Money Market Operations release: the overnight rates, SDF/MSF and net liquidity come out of the table."""
from orazio import macro

PAGE = """<b>Money Market Operations as on October 29, 2026</b><table>
<tr><th>MONEY MARKETS@</th><th>Volume (One Leg)</th><th>Weighted Average Rate</th><th>Range</th></tr>
<tr><td>A. Overnight Segment (I+II+III+IV)</td><td>7,37,187.01</td><td>5.51</td><td>4.00-5.95</td></tr>
<tr><td>I. Call Money</td><td>15,643.06</td><td>5.58</td><td>4.30-5.80</td></tr>
<tr><td>II. Triparty Repo</td><td>5,21,375.15</td><td>5.50</td><td>5.00-5.61</td></tr>
<tr><td>III. Market Repo</td><td>1,93,792.00</td><td>5.55</td><td>4.00-5.70</td></tr>
<tr><td>B. Term Segment</td></tr>
<tr><td>II. Triparty Repo</td><td>5,545.00</td><td>9.99</td><td>5.50-5.52</td></tr>
<tr><td>3. MSF#</td><td>Thu, 29/10/2026</td><td>1</td><td>Fri, 30/10/2026</td><td>9,205.00</td><td>5.75</td></tr>
<tr><td>4. SDF&Delta;#</td><td>Thu, 29/10/2026</td><td>1</td><td>Fri, 30/10/2026</td><td>1,74,418.00</td><td>5.25</td></tr>
<tr><td>3. MSF#</td></tr>
<tr><td>F. Net liquidity injected (outstanding including today's operations) [injection (+)/absorption (-)]*</td><td>-30,454.13</td></tr>
</table>"""


def test_parse_mmo_reads_overnight_rates_not_term_ones():
    assert macro.parse_mmo(PAGE) == {"date": "2026-10-29", "call": 5.58, "treps": 5.5, "repo": 5.55,
                                     "msf": 9205.0, "sdf": 174418.0, "net": -30454.13}


def test_parse_mmo_rejects_other_pages():
    assert macro.parse_mmo("<html>Result of Underwriting Auction</html>") is None
