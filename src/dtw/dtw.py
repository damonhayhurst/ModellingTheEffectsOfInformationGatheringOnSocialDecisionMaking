import math
from pandas import DataFrame, Series
from scipy import stats
from utils.masks import get_is_in_aois
from utils.paths import DTW_Z_V2_CSV
from utils.display import display
from utils.read_csv import read_from_analysis_file, read_from_dwell_file
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from utils.columns import *
from dtaidistance import dtw, dtw_ndim, preprocessing
from dtaidistance.innerdistance import CustomInnerDist, SquaredEuclidean
from itertools import combinations
from scipy.stats import zscore
from typing import List, Tuple

DWELL_DICT = {column: index for index, column in enumerate([np.nan] + DWELL_COLUMNS)}


def get_t_series_sequences_and_trials(dwell_df: DataFrame, analysis_df: DataFrame, z_norm: bool = False) -> Tuple[List, List]:
    t_series = get_t_series_dwell_sequences(dwell_df, analysis_df, z_norm)
    t_series_trials = [trial for trial in t_series.keys()]
    t_series_sequences = [t_series[trial] for trial in t_series_trials]
    return t_series_sequences, t_series_trials


def get_dtw_distance(dwell_df: DataFrame, analysis_df: DataFrame, to_file: str = None) -> DataFrame:
    t_series_sequences, t_series_trials = get_t_series_sequences_and_trials(dwell_df, analysis_df, z_norm=True)
    dtws = dtw_ndim.distance_matrix_fast(t_series_sequences, only_triu=True)
    distances = {}
    idx = 0
    for x in range(0, len(dtws)):
        for y in range(0, len(dtws[x])):
            if y is not np.nan:
                pid1, trial_id1 = t_series_trials[x]
                pid2, trial_id2 = t_series_trials[y]
                selected_aoi_1, selected_aoi_2 = analysis_df.loc[pid1, trial_id1][SELECTED_AOI], analysis_df.loc[pid2, trial_id2][SELECTED_AOI]
                trial_count_1, trial_count_2 = analysis_df.loc[pid1, trial_id1][TRIAL_COUNT], analysis_df.loc[pid2, trial_id2][TRIAL_COUNT]
                distances[idx] = {
                    PID_1: pid1, TRIAL_ID_1: trial_id1, TRIAL_COUNT_1: trial_count_1,
                    PID_2: pid2, TRIAL_ID_2: trial_id2, TRIAL_COUNT_2: trial_count_2,
                    SELECTED_AOI_1: selected_aoi_1, SELECTED_AOI_2: selected_aoi_2,
                    DISTANCE: dtws[x][y]
                }
                idx = idx + 1
    distance_df = DataFrame.from_dict(distances, orient='index')
    distance_df = distance_df.set_index([PID_1, TRIAL_ID_1, PID_2, TRIAL_ID_2])
    if to_file:
        save(distance_df, to_file)
    return distance_df


def get_ndim_distance(trial1: DataFrame, trial2: DataFrame, z_norm: bool = False):
    idx1, idx2 = trial1.index, trial2.index
    trial1.loc[idx1, SELF_LIE], trial2.loc[idx2, SELF_LIE] = get_is_in_aois(trial1, SELF_LIE).astype(int), get_is_in_aois(trial2, SELF_LIE).astype(int)
    trial1.loc[idx1, SELF_TRUE], trial2.loc[idx2, SELF_TRUE] = get_is_in_aois(trial1, SELF_TRUE).astype(int), get_is_in_aois(trial2, SELF_TRUE).astype(int)
    trial1.loc[idx1, OTHER_LIE], trial2.loc[idx2, OTHER_LIE] = get_is_in_aois(trial1, OTHER_LIE).astype(int), get_is_in_aois(trial2, OTHER_LIE).astype(int)
    trial1.loc[idx1, OTHER_TRUTH], trial2.loc[idx2, OTHER_TRUTH] = get_is_in_aois(trial1, OTHER_TRUTH).astype(int), get_is_in_aois(trial2, OTHER_TRUTH).astype(int)
    if z_norm:
        trial1[DWELL_TIME] = zscore(trial1[DWELL_TIME])
        trial2[DWELL_TIME] = zscore(trial2[DWELL_TIME])
    trial1_tuples = trial1.loc[idx1][[DWELL_TIME, SELF_LIE, SELF_TRUE, OTHER_LIE, OTHER_TRUTH]].itertuples(index=False, name=None)
    trial2_tuples = trial2.loc[idx2][[DWELL_TIME, SELF_LIE, SELF_TRUE, OTHER_LIE, OTHER_TRUTH]].itertuples(index=False, name=None)
    trial1_ndim = np.array([[dwell, *aois] for dwell, *aois in trial1_tuples], dtype=object)
    trial2_ndim = np.array([[dwell, *aois] for dwell, *aois in trial2_tuples], dtype=object)
    return dtw_ndim.distance(trial1_ndim, trial2_ndim)


def get_t_series_dwell_sequences(dwell_df: DataFrame, analysis_df: DataFrame, z_norm: bool = False):
    trials = analysis_df.index.unique()
    if z_norm:
        trial_seq_dict = {trial: stats.zscore(get_t_series_dwell_sequence(dwell_df.loc[trial]), axis=None) for trial in trials}
    else:
        trial_seq_dict = {trial: get_t_series_dwell_sequence(dwell_df.loc[trial]) for trial in trials}
    print("Trial sequence complete")
    return trial_seq_dict


def get_t_series_df(dwell_df: DataFrame, analysis_df: DataFrame):
    trials = analysis_df.index.unique()
    t_series_df = DataFrame()
    for trial in trials:
        t_series_df[trial] = get_t_series_row(dwell_df.loc[trial])
    return t_series_df


def get_t_series_row(trial: DataFrame):
    idx = trial.index
    trial[DWELL_TIME] = pd.to_timedelta(trial[DWELL_TIME], "ms")
    trial[DWELL_TIME_MS] = (trial[DWELL_TIME].dt.microseconds).astype(int)
    trial.loc[idx, SELF_LIE] = get_is_in_aois(trial, SELF_LIE).astype(int)
    trial.loc[idx, SELF_TRUE] = get_is_in_aois(trial, SELF_TRUE).astype(int)
    trial.loc[idx, OTHER_LIE] = get_is_in_aois(trial, OTHER_LIE).astype(int)
    trial.loc[idx, OTHER_TRUTH] = get_is_in_aois(trial, OTHER_TRUTH).astype(int)
    self_lie_seq, self_true_seq, other_lie_seq, other_truth_seq = [], [], [], []
    for time, self_lie, self_true, other_lie, other_truth in trial.loc[idx][[DWELL_TIME_MS, SELF_LIE, SELF_TRUE, OTHER_LIE, OTHER_TRUTH]].itertuples(index=False, name=None):
        for t in range(time):
            self_lie_seq.append(self_lie)
            self_true_seq.append(self_true)
            other_lie_seq.append(other_lie)
            other_truth_seq.append(other_truth)
    return self_lie_seq, self_true_seq, other_lie_seq, other_truth_seq


def get_t_series_dwell_sequence(trial: DataFrame, z_norm: bool = False):
    idx = trial.index
    trial[DWELL_TIME] = pd.to_timedelta(trial[DWELL_TIME], "ms")
    trial[DWELL_TIME_MS] = (trial[DWELL_TIME].dt.microseconds).astype(int)
    trial.loc[idx, SELF_LIE] = get_is_in_aois(trial, SELF_LIE).astype(int)
    trial.loc[idx, SELF_TRUE] = get_is_in_aois(trial, SELF_TRUE).astype(int)
    trial.loc[idx, OTHER_LIE] = get_is_in_aois(trial, OTHER_LIE).astype(int)
    trial.loc[idx, OTHER_TRUTH] = get_is_in_aois(trial, OTHER_TRUTH).astype(int)
    t_series = []
    for time, *aois in trial.loc[idx][[DWELL_TIME_MS, SELF_LIE, SELF_TRUE, OTHER_LIE, OTHER_TRUTH]].itertuples(index=False, name=None):
        for t in range(time):
            t_series.append(aois)
    return np.array(t_series)


def save(distance_df: DataFrame, path: str = DTW_Z_V2_CSV):
    distance_df.to_csv(path)
    print("DTW saved to %s" % path)


if __name__ == "__main__":
    dwell_df = read_from_dwell_file()
    analysis_df = read_from_analysis_file()
    distance_df = get_dtw_distance(dwell_df, analysis_df)
    display(distance_df)
