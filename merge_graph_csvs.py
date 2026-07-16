#!/usr/bin/env python3
import argparse
import csv
import glob
import os
import re
from collections import defaultdict

REGION_PATTERN = re.compile(r"^isebel-([^-]+)(?:-co-occurence)?-(edges|nodes)\.csv$")


def get_region(filename):
    base = os.path.basename(filename)
    match = REGION_PATTERN.match(base)
    if not match:
        raise ValueError(f"Unexpected filename format: {filename}")
    return match.group(1)


def collect_files(input_dir, exclude_cooccurrence=True, regions=None):
    files = sorted(glob.glob(os.path.join(input_dir, 'isebel-*.csv')))
    edge_files = []
    node_files = []
    for path in files:
        base = os.path.basename(path)
        if exclude_cooccurrence and 'co-occurence' in base:
            continue
        if regions is not None:
            region = get_region(path)
            if region not in regions:
                continue
        if base.endswith('-edges.csv'):
            edge_files.append(path)
        elif base.endswith('-nodes.csv'):
            node_files.append(path)
    return edge_files, node_files


def merge_csv_files(files, output_file):
    merged_rows = []
    fieldnames = []
    for path in files:
        region = get_region(path)
        with open(path, newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                continue
            for row in reader:
                row = dict(row)
                row['region'] = region
                merged_rows.append(row)
                for key in row.keys():
                    if key not in fieldnames:
                        fieldnames.append(key)
    if 'region' not in fieldnames:
        fieldnames.append('region')
    with open(output_file, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_rows)
    return len(merged_rows), fieldnames


def parse_args():
    parser = argparse.ArgumentParser(description='Merge graph CSV files with region metadata.')
    parser.add_argument('--input-dir', default='.', help='Directory containing the CSV files.')
    parser.add_argument('--output-dir', default='.', help='Directory to write merged CSV files.')
    parser.add_argument('--no-cooccur', dest='exclude_cooccurrence', action='store_false', help='Do not exclude co-occurence files.')
    parser.add_argument('--regions', nargs='+', metavar='REGION',
                        help='Only merge these regions (e.g. --regions denmark mecklenburg).')
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    regions = set(args.regions) if args.regions else None
    edge_files, node_files = collect_files(args.input_dir, exclude_cooccurrence=args.exclude_cooccurrence, regions=regions)
    if not edge_files and not node_files:
        raise SystemExit('No CSV files found to merge.')

    edges_output = os.path.join(args.output_dir, 'isebel-merged-edges.csv')
    nodes_output = os.path.join(args.output_dir, 'isebel-merged-nodes.csv')

    edge_count, edge_fields = merge_csv_files(edge_files, edges_output)
    node_count, node_fields = merge_csv_files(node_files, nodes_output)

    print(f'Merged {edge_count} edge rows into {edges_output}')
    print(f'Merged {node_count} node rows into {nodes_output}')
    print('edge fieldnames:', edge_fields)
    print('node fieldnames:', node_fields)


if __name__ == '__main__':
    main()
