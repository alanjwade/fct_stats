#!/usr/bin/env python3
"""Check specific cells I2 and I3 in Girls Track sheet."""

from odf import opendocument, table, text
from pathlib import Path

def get_cell_text(cell):
    try:
        text_content = []
        for p in cell.getElementsByType(text.P):
            for node in p.childNodes:
                if node.nodeType == node.TEXT_NODE:
                    text_content.append(str(node.data))
        return ' '.join(text_content).strip()
    except:
        return ''

ods_path = Path('tmp/2025 Track & Field Performance List.xlsx.ods')
doc = opendocument.load(str(ods_path))

# Get the Girls Track sheet
tables = doc.spreadsheet.getElementsByType(table.Table)
sheet = tables[0]

print(f"Sheet: {sheet.getAttribute('name')}\n")

rows = sheet.getElementsByType(table.TableRow)

# Look at rows 1-5 (Excel rows 2-6) and show columns A-N
for row_idx in range(5):
    row = rows[row_idx]
    cells = row.getElementsByType(table.TableCell)
    expanded_cells = []
    
    for cell in cells:
        repeat_count = cell.getAttribute('numbercolumnsrepeated')
        repeat = int(repeat_count) if repeat_count else 1
        for _ in range(repeat):
            expanded_cells.append(cell)
    
    print(f"Row {row_idx + 1} (Excel row {row_idx + 1}):")
    for col_idx in range(min(14, len(expanded_cells))):
        text = get_cell_text(expanded_cells[col_idx])
        col_letter = chr(ord('A') + col_idx)
        display = text[:40] if text else "(empty)"
        print(f"  {col_letter}{row_idx + 1}: {display}")
    print()
