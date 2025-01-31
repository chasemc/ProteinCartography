#!/usr/bin/env python
from bioservices import UniProt
import argparse
import pandas as pd
from requests import get, post
from time import sleep
import sys

# only import these functions when using import *
__all__ = ["map_refseqids_bioservices", "map_refseqids_rest"]

# check through these default databases
DEFAULT_DBS = ["EMBL-GenBank-DDBJ_CDS", "RefSeq_Protein"]

# id mapping link
UNIPROT_IDMAPPING_API = "https://rest.uniprot.org/idmapping"

# requests constants
REQUESTS_TRIES = 0
REQUESTS_LIMIT = 10
REQUESTS_SLEEP_TIME = 30

REQUESTS_HEADER = {
    "User-Agent": "ProteinCartography/0.4 (Arcadia Science) python-requests/2.0.1",
}


# parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="path to input .txt file containing one accession per line.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="path to destination .txt file where uniquely-mapped Uniprot accessions will be printed.",
    )
    parser.add_argument(
        "-d",
        "--databases",
        nargs="+",
        default=DEFAULT_DBS,
        help=f"which databases to use for mapping. defaults to {DEFAULT_DBS}",
    )
    parser.add_argument("-s", "--service", default="rest", help="how to fetch mapping")
    args = parser.parse_args()
    return args


# takes a list of IDs and maps them to Uniprot using bioservices
# might make a more generalizable version of this and put it somewhere else
def map_refseqids_bioservices(
    input_file: str, output_file: str, query_dbs: list, return_full=False
):
    """
    Takes an input .txt file of accessions and maps to UniProt accessions.

    Args:
        input_file (str): path to input .txt file containing one accession per line.
        output_file (str): path to destination .txt file.
        query_dbs (list): list of valid databases to query using the Uniprot ID mapping API.
            Each database will be queried individually.
            The results are compiled and unique results are printed to output_file.
    """

    # make object that references UniProt database
    u = UniProt()

    # open the input file to extract ids
    with open(input_file, "r") as f:
        ids = f.read().splitlines()

    if len(ids) > 100000:
        ids = ids[0:100000]

    # make an empty collector dataframe for mapping
    dummy_df = pd.DataFrame()

    # for each query database, map
    for i, db in enumerate(query_dbs):
        # u.mapping returns a gross json file
        results = u.mapping(db, "UniProtKB", query=",".join(ids))

        # pandas can normalize the json and make it more tractable
        results_df = pd.json_normalize(results["results"])

        # if there are no results, move on
        if len(results_df) == 0:
            continue

        # if it's the first database, replace it with the dummy dataframe
        if i == 0:
            dummy_df = results_df
        # otherwise append to the dataframe
        else:
            dummy_df = pd.concat([dummy_df, results_df], axis=0)

    # extract just the unique Uniprot accessions
    hits = dummy_df["to.primaryAccession"].unique()

    # save those accessions to a .txt file
    with open(output_file, "w+") as f:
        f.writelines(hit + "\n" for hit in hits)

    if return_full:
        return dummy_df


# Example curl POST request
"""
% curl --request POST 'https://rest.uniprot.org/idmapping/run' --form 'ids="P21802,P12345"' --form 'from="UniProtKB_AC-ID"' --form 'to="UniRef90"'
"""


def map_refseqids_rest(
    input_file: str, output_file: str, query_dbs: list, return_full=False
):
    """
    Takes an input .txt file of accessions and maps to UniProt accessions.

    Args:
        input_file (str): path to input .txt file containing one accession per line.
        output_file (str): path to destination .txt file.
        query_dbs (list): list of valid databases to query using the Uniprot ID mapping API.
            Each database will be queried individually.
            The results are compiled and unique results are printed to output_file.
        return_full (bool): whether to return all of the results as a dataframe
    """
    # open the input file to extract ids
    with open(input_file, "r") as f:
        input_lines = f.read().splitlines()
        input_ids = list(set(input_lines))
        input_string = ",".join(input_ids)

    dummy_df = pd.DataFrame()

    for i, db in enumerate(query_dbs):
        ticket = post(
            f"{UNIPROT_IDMAPPING_API}/run",
            {"ids": input_string, "from": db, "to": "UniProtKB"},
            headers=REQUESTS_HEADER,
        ).json()

        # poll until the job was successful or failed
        repeat = True
        tries = REQUESTS_TRIES
        limit = REQUESTS_LIMIT
        sleep_time = REQUESTS_SLEEP_TIME
        while repeat and tries < limit:
            status = get(
                f'{UNIPROT_IDMAPPING_API}/status/{ticket["jobId"]}',
                headers=REQUESTS_HEADER,
            ).json()

            # wait a short time between poll requests
            sleep(sleep_time)
            tries += 1
            repeat = "results" not in status

        if tries == 10:
            sys.exit(
                f"The ticket failed to complete after {tries * sleep_time} seconds."
            )

        results = get(f'{UNIPROT_IDMAPPING_API}/stream/{ticket["jobId"]}').json()
        results_df = pd.DataFrame(results["results"])

        # if there are no results, move on
        if len(results_df) == 0:
            continue

        # if it's the first database, replace it with the dummy dataframe
        if i == 0:
            dummy_df = results_df
        # otherwise append to the dataframe
        else:
            dummy_df = pd.concat([dummy_df, results_df], axis=0)

    # extract just the unique Uniprot accessions
    hits = dummy_df["to"].unique()

    # save those accessions to a .txt file
    with open(output_file, "w+") as f:
        f.writelines(hit + "\n" for hit in hits)

    if return_full:
        return dummy_df


# run this if called from the interpreter
def main():
    # parse arguments
    args = parse_args()

    # collect arguments individually
    input_file = args.input
    output_file = args.output
    query_dbs = args.databases
    service = args.service

    if service == "bioservices":
        # send to map_refseqids
        map_refseqids_bioservices(input_file, output_file, query_dbs)
    else:
        map_refseqids_rest(input_file, output_file, query_dbs)


# check if called from interpreter
if __name__ == "__main__":
    main()
