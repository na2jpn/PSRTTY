# DXCC display names

Entity identity and prefix matching remain based on psrtty/data/contest_prefixes.json and its existing licence. Localized territory names are generated from Unicode CLDR via Babel; runtime does not require Babel/pycountry. Subdivision names use explicit overrides where available. Rare island/entity proper names without a translation retain the database name; a parent country is never substituted for a distinct DXCC entity. This display data does not change contest scoring or the transmitted/received text. JD1 and /JD1 remain blank where the existing resolver cannot distinguish Ogasawara/Minami Torishima. No location is inferred from the user's own licence.

Unicode CLDR: https://cldr.unicode.org/ — Unicode licence: https://www.unicode.org/license.txt
