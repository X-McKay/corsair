# UI source provenance

Adapted from the user-designated [X-McKay/infosec-harness UI](https://github.com/X-McKay/infosec-harness/tree/52aa2ac64f3d81139b609f18890ac52950d02933/ui), revision `52aa2ac64f3d81139b609f18890ac52950d02933`:

- `src/lib/format.ts` preserves its missing-measurement and duration/date formatting helpers.
- `src/lib/theme.ts` adapts its system/light/dark preference helpers with a Corsair storage key.
- `src/components/ThemeProvider.tsx` adapts its resilient native media-query and storage handling.
- Sidebar navigation, neutral light/dark palette, violet accents, evidence qualification, and separate inspection views inform the layout. The palette follows the reference `src/index.css`; Corsair-specific pages, responsive styling, and API integration are new.

The source checkout did not contain a repository-wide license file. This reuse follows the repository owner's explicit request; it does not assert a new license over the source. No external fonts, analytics, remote assets, or infosec-harness API assumptions are carried over.

The browser contrast audit (`e2e/support/contrast.ts`) is also copied from that reference UI and used to check the adapted palette.
