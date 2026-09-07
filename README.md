# Make Contact Sheet

A Python script to create an authentic rendering of a traditional film/negative contact sheet from a folder of images.

The script supports both **35mm film** and **120 medium-format film in the 6x6 format**. The 120 6x6 option is particularly well suited to square source images.

The following standard image and camera RAW formats are currently supported:

| Extension | Description |
| --- | --- |
| .jpg | Joint Photographic Experts Group |
| .jpeg | Joint Photographic Experts Group |
| .png | Portable Network Graphics |
| .tif | Tagged Image File Format |
| .tiff | Tagged Image File Format |
| .cr2 | Canon Raw (v.2) |
| .cr3 | Canon Raw (v.3) |
| .nef | Nikon Electronic Format |
| .arw | Sony Alpha Raw |
| .dng | Adobe Digital Negative |
| .raf | Fujifilm Raw |
| .orf | Olympus Raw Format |
| .rw2 | Panasonic Raw |
| .pef | Pentax Electronic File |
| .srw | Samsung Raw |

## Requirements

This project requires Python 3.11 or newer.

Third-party dependencies are:

- `Pillow`
- `rawpy`

See the file `requirements.txt` in the repository for version details.

## Installation

Clone the repository:

```bash
git clone https://github.com/csalvaggio/make_contact_sheet.git
```

Create and activate a virtual environment:

```bash
cd make_contact_sheet
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

## Film Formats

The contact sheet may be rendered using either **35mm film** or **120 medium-format film in the 6x6 format**.

35mm is the default:

```bash
python3 make_contact_sheet.py images
```

The simulated 35mm layout contains six frames per strip and six strips per sheet, for a total of 36 frames per contact sheet.

To create a 120 6x6 contact sheet:

```bash
python3 make_contact_sheet.py images --film-format 120-6x6
```

The aliases `120` and `6x6` may also be used:

```bash
python3 make_contact_sheet.py images --film-format 120
```

The simulated 120 6x6 layout contains three frames per strip and four strips per sheet, for a total of 12 frames per contact sheet.

| Film format | Frames per strip | Strips per sheet | Frames per sheet |
| --- | ---: | ---: | ---: |
| 35mm | 6 | 6 | 36 |
| 120 6x6 | 3 | 4 | 12 |

The default simulated film-edge markings depend on the selected film format:

- 35mm: `KODAK SAFETY FILM 5035`
- 120 6x6: `KODAK 200`

The film-edge name may be overridden with `--film-name`:

```bash
python3 make_contact_sheet.py images \
    --film-format 120 \
    --film-name "ILFORD FP5 PLUS"
```

## Image Ordering

Images are normally placed on the contact sheet in alphabetical order by filename.

For JPEG images containing the custom headshot-kiosk XMP metadata, the script can instead order the images by name. If every image in the input directory contains a non-empty `LastName` field, the images are sorted case-insensitively by:

1. `LastName`
2. `FirstName`
3. filename

The filename is used only as a final tie breaker when both the last name and first name are the same, or when the first name is not present.

If one or more images do not contain a `LastName` field, the entire collection falls back to the original alphabetical filename ordering. This avoids mixing metadata-based and filename-based ordering within the same contact sheet set.

The custom XMP fields use the headshot-kiosk namespace:

```text
https://www.rit.edu/ns/headshot-kiosk/1.0/
```

No additional third-party dependency is required for this feature.

## Documentation

Full help/documentation may be viewed from the command line by typing:

```bash
python3 make_contact_sheet.py --help
```

## License

This project is licensed under the GNU General Public License v3.0.  
See `LICENSE` for details.

## Contact

### Author

Carl Salvaggio, Ph.D.  
Professor of Imaging Science  
Director, Digital Imaging and Remote Sensing (DIRS) Laboratory

### E-mail

carl.salvaggio@rit.edu

### Organization

Chester F. Carlson Center for Imaging Science  
Rochester Institute of Technology  
Rochester, New York, 14623  
United States
