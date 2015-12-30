from collections import defaultdict
import numpy as np


class Corpus():
    _keys_frequency = None

    def __init__(self, skip=-1, out_of_vocabulary=-2):
        """ The Corpus helps with tasks involving integer representations of
        words. This object is used to filter, subsample, and convert loose
        word indices to compact word indices.

        'Loose' word arrays are word indices given by a tokenizer. The word
        index is not necessarily representative of word's frequency rank, and
        so loose arrays tend to have 'gaps' of unused indices, which can make
        models less memory efficient. As a result, this class helps convert
        a loose array to a 'compact' one where the most common words have low
        indices, and the most infrequent have high indices.

        Corpus maintains a count of how many of each word it has seen so
        that it can later selectively filter frequent or rare words. However,
        since word popularity rank could change with incoming data the word
        index count must be updated fully and `self.finalize()` must be called
        before any filtering and subsampling operations can happen.

        Arguments
        ---------
        skip : int, default=-1
            Token index to replace whenever we want to skip the current frame.
            Particularly useful when subsampling words or when padding a
            sentence.
        out_of_vocabulary : int, default=-2
            Token index to replace whenever we encounter a rare or unseen word.
            Instead of skipping the token, we mark as an out of vocabulary
            word.

        >>> corpus = Corpus()
        >>> words_raw = np.random.randint(100, size=25)
        >>> corpus.update_word_count(words_raw)
        >>> corpus.finalize()
        >>> words_compact = corpus.to_compact(words_raw)
        >>> words_pruned = corpus.filter_count(words_compact, min_count=2)
        >>> # words_sub = corpus.subsample_frequent(words_pruned, thresh=1e-5)
        >>> words_loose = corpus.to_loose(words_pruned)
        >>> not_oov = words_loose > -1
        >>> np.all(words_loose[not_oov] == words_raw[not_oov])
        True
        """
        self.counts_loose = defaultdict(int)
        self._finalized = False
        self.special = dict(out_of_vocabulary=out_of_vocabulary,
                            skip=skip)

    def update_word_count(self, loose_array):
        """ Update the corpus word counts given a loose array of word indices.
        Can be called multiple times, but once `finalize` is called the word
        counts cannot be updated.

        Arguments
        ---------
        loose_array : int array
            Array of word indices.

        >>> corpus = Corpus()
        >>> corpus.update_word_count(np.arange(10))
        >>> corpus.update_word_count(np.arange(8))
        >>> corpus.counts_loose[0]
        2
        >>> corpus.counts_loose[9]
        1
        """
        self._check_unfinalized()
        uniques, counts = np.unique(np.ravel(loose_array), return_counts=True)
        for k, v in zip(uniques, counts):
            self.counts_loose[k] += v

    def _get_loose_keys_ordered(self):
        """ Get the loose keys in order of decreasing frequency"""
        loose_counts = sorted(self.counts_loose.items(), key=lambda x: x[1],
                              reverse=True)
        keys = np.array(loose_counts)[:, 0]
        counts = np.array(loose_counts)[:, 1]
        order = np.argsort(counts)[::-1].astype('int32')
        keys, counts = keys[order], counts[order]
        n_keys = keys.shape[0]
        return keys, counts, n_keys

    def finalize(self):
        """ Call `finalize` once done updating word counts. This means the
        object will no longer accept new word count data, but the loose
        to compact index mapping can be computed. This frees the object to
        filter, subsample, and compactify incoming word arrays.

        >>> corpus = Corpus()

        We'll update the word counts, making sure that word index 2
        is the most common word index.
        >>> corpus.update_word_count(np.arange(1) + 2)
        >>> corpus.update_word_count(np.arange(3) + 2)
        >>> corpus.update_word_count(np.arange(10) + 2)
        >>> corpus.update_word_count(np.arange(8) + 2)
        >>> corpus.counts_loose[2]
        4

        The corpus has not been finalized yet, and so the compact mapping
        has not yet been computed.
        >>> corpus.keys_counts[0]
        Traceback (most recent call last):
            ...
        AttributeError: Corpus instance has no attribute 'keys_counts'
        >>> corpus.finalize()
        >>> corpus.keys_counts[0]
        4
        >>> corpus.loose_to_compact[2]
        0
        >>> corpus.loose_to_compact[3]
        2
        """
        # Return the loose keys and counts in descending count order
        # so that the counts arrays is already in compact order
        self.keys_loose, counts, n_keys = self._get_loose_keys_ordered()
        self.keys_compact = np.arange(n_keys).astype('int32')
        self.keys_counts = counts
        self.loose_to_compact = {l: c for l, c in
                                 zip(self.keys_loose, self.keys_compact)}
        self.compact_to_loose = {c: l for l, c in
                                 self.loose_to_compact.items()}
        self._finalized = True

    @property
    def keys_frequency(self):
        if self._keys_frequency is None:
            f = self.keys_counts * 1.0 / np.sum(self.keys_counts)
            self._keys_frequency = f
        return self._keys_frequency

    def _check_finalized(self):
        msg = "self.finalized() must be called before any other array ops"
        assert self._finalized, msg

    def _check_unfinalized(self):
        msg = "Cannot update word counts after self.finalized()"
        msg += "has been called"
        assert not self._finalized, msg

    def filter_count(self, words_compact, min_count=20000, max_count=0,
                     max_replacement=None, min_replacement=None):
        """ Replace word indices below min_count with the pad index.

        Arguments
        ---------
        words_compact: int array
            Source array whose values will be replaced. This is assumed to
            already be converted into a compact array with `to_compact`.
        min_count : int
            Replace words less frequently occuring than this count. This
            defines the threshold for what words are very rare
        max_count : int
            Replace words occuring more frequently than this count. This
            defines the threshold for very frequent words
        min_replacement : int, default is out_of_vocabulary
            Replace words less than min_count with this.
        max_replacement : int, default is out_of_vocabulary
            Replace words greater than max_count with this.

        >>> corpus = Corpus()

        Make 1000 word indices with index < 100 and update the word counts.
        >>> word_indices = np.random.randint(100, size=1000)
        >>> corpus.update_word_count(word_indices)
        >>> corpus.finalize()  # any word indices above 99 will be filtered

        Now create a new text, but with some indices above 100
        >>> word_indices = np.random.randint(200, size=1000)
        >>> word_indices.max() < 100
        False

        Remove words that have never appeared in the original corpus.
        >>> filtered = corpus.filter_count(word_indices, min_count=1)
        >>> filtered.max() < 100
        True

        We can also remove highly frequent words.
        >>> filtered = corpus.filter_count(word_indices, max_count=2)
        >>> len(np.unique(word_indices)) > len(np.unique(filtered))
        True
        """
        self._check_finalized()
        ret = words_compact.copy()
        if min_replacement is None:
            min_replacement = self.special['out_of_vocabulary']
        if max_replacement is None:
            max_replacement = self.special['out_of_vocabulary']
        if min_count:
            # Find first index with count less than min_count
            min_idx = np.argmax(self.keys_counts < min_count)
            # Replace all indices greater than min_idx
            ret[ret > min_idx] = min_replacement
        if max_count:
            # Find first index with count less than max_count
            max_idx = np.argmax(self.keys_counts < max_count)
            # Replace all indices less than max_idx
            ret[ret < max_idx] = max_replacement
        return ret

    def subsample_frequent(self, words_compact, threshold=1e-5):
        """ Subsample the most frequent words. This aggressively
        replaces words with frequencies higher than `threshold`. Words
        are replaced with the out_of_vocabulary token.

        Words will be replaced with probability as a function of their
        ferquency in the training corpus:
        .. math :: p(w) = 1.0 - \sqrt{\frac{threshold}{f(w)}}

        Arguments
        ---------
        words_compact: int array
            The input array to subsample.
        threshold: float in [0, 1]
            Words with frequencies higher than this will be increasingly
            subsampled.

        >>> corpus = Corpus()
        >>> word_indices = (np.random.power(5.0, size=1000) * 100).astype('i')
        >>> corpus.update_word_count(word_indices)
        >>> corpus.finalize()
        >>> compact = corpus.to_compact(word_indices)
        >>> sampled = corpus.subsample_frequent(compact, threshold=1e-2)
        >>> np.sum(sampled == 0) < np.sum(compact == 0)
        True

        .. [1] Distributed Representations of Words and Phrases and
               their Compositionality. Mikolov, Tomas and Sutskever, Ilya
               and Chen, Kai and Corrado, Greg S and Dean, Jeff
               Advances in Neural Information Processing Systems 26
        """
        self._check_finalized()
        prob = 1.0 - np.sqrt(threshold / self.keys_frequency)
        prob = np.clip(prob, 0, 1)
        prob = fast_replace(words_compact, self.keys_compact, prob)
        draw = np.random.uniform(size=prob.shape)
        ret = words_compact.copy()
        ret[prob > draw] = self.special['skip']
        return ret

    def to_compact(self, word_loose):
        """ Convert a loose word index matrix to a compact array using
        a fixed loose to dense mapping. Out of vocabulary word indices
        will be replaced by the out of vocabulary index. The most common
        index will be mapped to 0, the next most common to 1, and so on.

        Arguments
        ---------
        word_loose : int array
            Input loose word array to be converted into a compact array.

        >>> corpus = Corpus()
        >>> word_indices = np.random.randint(100, size=1000)
        >>> n_words = len(np.unique(word_indices))
        >>> corpus.update_word_count(word_indices)
        >>> corpus.finalize()  # any word indices above 99 will be filtered
        >>> word_compact = corpus.to_compact(word_indices)
        >>> np.argmax(np.bincount(word_compact)) == 0
        True

        The most common word in the training set will be mapped to zero.
        >>> most_common = np.argmax(np.bincount(word_indices))
        >>> least_common = np.argmin(np.bincount(word_indices))
        >>> corpus.loose_to_compact[most_common] == 0
        True

        Out of vocabulary indices will be mapped to -1.
        >>> word_indices = np.random.randint(150, size=1000)
        >>> word_compact = corpus.to_compact(word_indices)
        >>> -1 in word_compact
        True
        """
        self._check_finalized()
        keys = self.keys_loose.copy()
        reps = self.keys_compact.copy()
        uniques = np.unique(word_loose)
        # Find the out of vocab indices
        oov = np.setdiff1d(uniques, keys, assume_unique=True)
        keys = np.concatenate((keys, oov))
        reps = np.concatenate((reps, np.zeros_like(oov) - 1))
        compact = fast_replace(word_loose, keys, reps)
        return compact

    def to_loose(self, word_compact):
        """ Convert a compacted array back into a loose array.

        Arguments
        ---------
        word_compact : int array
            Input compacted word array to be converted into a loose array.

        >>> corpus = Corpus()
        >>> word_indices = np.random.randint(100, size=1000)
        >>> corpus.update_word_count(word_indices)
        >>> corpus.finalize()
        >>> word_compact = corpus.to_compact(word_indices)
        >>> word_loose = corpus.to_loose(word_compact)
        >>> np.all(word_loose == word_indices)
        True
        """
        self._check_finalized()
        uniques = np.unique(word_compact)
        # Find the out of vocab indices
        oov = np.setdiff1d(uniques, self.keys_compact, assume_unique=True)
        msg = "Found keys in `word_compact` not present in the corpus. "
        msg += " Is this actually a compacted array?"
        assert np.all(oov < 0), msg
        loose = fast_replace(word_compact, self.keys_compact, self.keys_loose)
        special = word_compact < 0
        loose[special] = word_compact[special]
        return loose


def fast_replace(data, keys, values, skip_checks=False):
    """ Do a search-and-replace in array `data`.

    Arguments
    ---------
    data : int array
        Array of integers
    keys : int array
        Array of keys inside of `data` to be replaced
    values : int array
        Array of values that replace the `keys` array
    skip_checks : bool, default=False
        Optionally skip sanity checking the input.

    >>> fast_replace(np.arange(5), np.arange(5), np.arange(5)[::-1])
    array([4, 3, 2, 1, 0])
    """
    assert np.allclose(keys.shape, values.shape)
    if not skip_checks:
        msg = "data has elements not in keys"
        assert data.max() <= keys.max(), msg
    sdx = np.argsort(keys)
    keys, values = keys[sdx], values[sdx]
    idx = np.digitize(data, keys, right=True)
    new_data = values[idx]
    return new_data