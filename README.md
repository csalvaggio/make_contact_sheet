# Make Contact Sheet

A Python script to create an authentic rendering of a traditional film/negative contact sheet from a folder of images.

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
| .raf | Fujifile Raw |
| .orf | Olympus Raw Format |
| .rw2 | Panasonic Raw |
| .pef | Pentax Electronic File |
| .srw | Samsung Raw |

## Requirements

This project requires Python 3.11 or newer.

Third-party dependencies are:

- `opencv-python`
- `Pillow`
- `rawpy`

See `requirements.txt` for version details.

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
