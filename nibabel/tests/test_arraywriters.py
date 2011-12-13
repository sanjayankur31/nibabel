""" Testing array writer objects

Array writers have init signature::

    def __init__(self, array, out_dtype=None, order='F')

and methods

* to_fileobj(fileobj, offset=None)

They do have attributes:

* array
* out_dtype
* order

They may have attributes:

* slope
* inter

They are designed to write arrays to a fileobj with reasonable memory
efficiency.

Subclasses of array writers may be able to scale the array or apply an
intercept, or do something else to make sense of conversions between float and
int, or between larger ints and smaller.
"""

import numpy as np

from ..py3k import BytesIO

from ..arraywriters import (SlopeInterArrayWriter, SlopeArrayWriter,
                            WriterError, ScalingError, ArrayWriter,
                            make_array_writer, get_slope_inter)

from ..volumeutils import array_from_file, apply_read_scaling

from numpy.testing import (assert_array_almost_equal,
                           assert_array_equal)

from nose.tools import (assert_true, assert_false,
                        assert_equal, assert_not_equal,
                        assert_raises)


FLOAT_TYPES = np.sctypes['float']
COMPLEX_TYPES = np.sctypes['complex']
INT_TYPES = np.sctypes['int']
UINT_TYPES = np.sctypes['uint']
CFLOAT_TYPES = FLOAT_TYPES + COMPLEX_TYPES
IUINT_TYPES = INT_TYPES + UINT_TYPES
NUMERIC_TYPES = CFLOAT_TYPES + IUINT_TYPES


def round_trip(writer, order='F', nan2zero=True, apply_scale=True):
    sio = BytesIO()
    arr = writer.array
    writer.to_fileobj(sio, order, nan2zero=nan2zero)
    data_back = array_from_file(arr.shape, writer.out_dtype, sio, order=order)
    slope, inter = get_slope_inter(writer)
    if apply_scale:
        data_back = apply_read_scaling(data_back, slope, inter)
    return data_back


def test_arraywriters():
    # Test initialize
    # Simple cases
    for klass in (SlopeInterArrayWriter, SlopeArrayWriter, ArrayWriter):
        for type in NUMERIC_TYPES:
            arr = np.arange(10, dtype=type)
            aw = klass(arr)
            assert_true(aw.array is arr)
            assert_equal(aw.out_dtype, arr.dtype)
            assert_array_equal(arr, round_trip(aw))
            # Byteswapped is OK
            bs_arr = arr.byteswap().newbyteorder('S')
            bs_aw = klass(bs_arr)
            assert_array_equal(bs_arr, round_trip(bs_aw))
            bs_aw2 = klass(bs_arr, arr.dtype)
            assert_array_equal(bs_arr, round_trip(bs_aw2))
            # 2D array
            arr2 = np.reshape(arr, (2, 5))
            a2w = klass(arr2)
            # Default out - in order is Fortran
            arr_back = round_trip(a2w)
            assert_array_equal(arr2, arr_back)
            arr_back = round_trip(a2w, 'F')
            assert_array_equal(arr2, arr_back)
            # C order works as well
            arr_back = round_trip(a2w, 'C')
            assert_array_equal(arr2, arr_back)
            assert_true(arr_back.flags.c_contiguous)


def test_special_rt():
    # Test that zeros; none finite - round trip to zeros
    for arr in (np.array([np.inf, np.nan, -np.inf]),
                np.zeros((3,))):
        for in_dtt in FLOAT_TYPES:
            for out_dtt in IUINT_TYPES:
                for klass in (ArrayWriter, SlopeArrayWriter,
                              SlopeInterArrayWriter):
                    aw = klass(arr.astype(in_dtt), out_dtt)
                    assert_equal(get_slope_inter(aw), (1, 0))
                    assert_array_equal(round_trip(aw), 0)


def test_slope_inter_castable():
    # Test scaling for arraywriter instances
    # Test special case of all zeros
    for in_dtt in FLOAT_TYPES + IUINT_TYPES:
        for out_dtt in NUMERIC_TYPES:
            for klass in (ArrayWriter, SlopeArrayWriter, SlopeInterArrayWriter):
                arr = np.zeros((5,), dtype=in_dtt)
                aw = klass(arr, out_dtt) # no error
    # Test special case of none finite
    arr = np.array([np.inf, np.nan, -np.inf])
    for in_dtt in FLOAT_TYPES:
        for out_dtt in FLOAT_TYPES + IUINT_TYPES:
            for klass in (ArrayWriter, SlopeArrayWriter, SlopeInterArrayWriter):
                aw = klass(arr.astype(in_dtt), out_dtt) # no error
    for in_dtt, out_dtt, arr, slope_only, slope_inter, neither in (
        (np.float32, np.float32, 1, True, True, True),
        (np.float64, np.float32, 1, True, True, True),
        (np.float32, np.complex128, 1, True, True, True),
        (np.uint32, np.complex128, 1, True, True, True),
        (np.int64, np.float32, 1, True, True, True),
        (np.float32, np.int16, 1, True, True, False),
        (np.complex128, np.float32, 1, False, False, False),
        (np.complex128, np.int16, 1, False, False, False),
        (np.uint8, np.int16, 1, True, True, True),
        # The following tests depend on the input data
        (np.uint16, np.int16, 1, True, True, True), # 1 is in range
        (np.uint16, np.int16, 2**16-1, True, True, False), # This not in range
        (np.uint16, np.int16, (0, 2**16-1), True, True, False),
        (np.uint16, np.uint8, 1, True, True, True),
        (np.int16, np.uint16, 1, True, True, True), # in range
        (np.int16, np.uint16, -1, True, True, False), # flip works for scaling
        (np.int16, np.uint16, (-1, 1), False, True, False), # not with +-
        (np.int8, np.uint16, 1, True, True, True), # in range
        (np.int8, np.uint16, -1, True, True, False), # flip works for scaling
        (np.int8, np.uint16, (-1, 1), False, True, False), # not with +-
    ):
        # data for casting
        data = np.array(arr, dtype=in_dtt)
        # With scaling but no intercept
        if slope_only:
            aw = SlopeArrayWriter(data, out_dtt)
        else:
            assert_raises(WriterError, SlopeArrayWriter, data, out_dtt)
        # With scaling and intercept
        if slope_inter:
            aw = SlopeInterArrayWriter(data, out_dtt)
        else:
            assert_raises(WriterError, SlopeInterArrayWriter, data, out_dtt)
        # With neither
        if neither:
            aw = ArrayWriter(data, out_dtt)
        else:
            assert_raises(WriterError, ArrayWriter, data, out_dtt)


def test_calculate_scale():
    # Test for special cases in scale calculation
    npa = np.array
    SIAW = SlopeInterArrayWriter
    SAW = SlopeArrayWriter
    # Offset handles scaling when it can
    aw = SIAW(npa([-2, -1], dtype=np.int8), np.uint8)
    assert_equal(get_slope_inter(aw), (1.0, -2.0))
    # Sign flip handles this case
    aw = SAW(npa([-2, -1], dtype=np.int8), np.uint8)
    assert_equal(get_slope_inter(aw), (-1.0, 0.0))
    # Case where offset handles scaling
    aw = SIAW(npa([-1, 1], dtype=np.int8), np.uint8)
    assert_equal(get_slope_inter(aw), (1.0, -1.0))
    # Can't work for no offset case
    assert_raises(WriterError, SAW, npa([-1, 1], dtype=np.int8), np.uint8)
    # Offset trick can't work when max is out of range
    aw = SIAW(npa([-1, 255], dtype=np.int16), np.uint8)
    assert_not_equal(get_slope_inter(aw), (1.0, -1.0))


def test_no_offset_scale():
    # Specific tests of no-offset scaling
    SAW = SlopeArrayWriter
    for data in ((-128, 127),
                  (-128, 126),
                  (-128, -127),
                  (126, 127),
                  (-127, 127)):
        aw = SAW(np.array(data, dtype=np.float32), np.int8)
        assert_equal(aw.slope, 1.0)
    aw = SAW(np.array([-126, 127 * 2.0], dtype=np.float32), np.int8)
    assert_equal(aw.slope, 2)
    aw = SAW(np.array([-128 * 2.0, 127], dtype=np.float32), np.int8)
    assert_equal(aw.slope, 2)


def test_io_scaling():
    # Test scaling works for max, min when going from larger to smaller type,
    # and from float to integer.
    bio = BytesIO()
    for in_type, out_type, err in ((np.int16, np.int16, None),
                                   (np.int16, np.int8, None),
                                   (np.uint16, np.uint8, None),
                                   (np.int32, np.int8, None),
                                   (np.float32, np.uint8, None),
                                   (np.float32, np.int16, None)):
        out_dtype = np.dtype(out_type)
        arr = np.zeros((3,), dtype=in_type)
        info = np.finfo(in_type) if arr.dtype.kind == 'f' else np.iinfo(in_type)
        arr[0], arr[1] = info.min, info.max
        aw = SlopeInterArrayWriter(arr, out_dtype, calc_scale=False)
        if not err is None:
            assert_raises(err, aw.calc_scale)
            continue
        aw.calc_scale()
        aw.to_fileobj(bio)
        bio.seek(0)
        arr2 = array_from_file(arr.shape, out_dtype, bio)
        arr3 = apply_read_scaling(arr2, aw.slope, aw.inter)
        # Max rounding error for integer type
        max_miss = aw.slope / 2.
        assert_true(np.all(np.abs(arr - arr3) <= max_miss))
        bio.truncate(0)
        bio.seek(0)


def test_nan2zero():
    # Test conditions under which nans written to zero
    arr = np.array([np.nan, 99.], dtype=np.float32)
    aw = SlopeInterArrayWriter(arr, np.float32)
    data_back = round_trip(aw)
    assert_array_equal(np.isnan(data_back), [True, False])
    # nan2zero ignored for floats
    data_back = round_trip(aw, nan2zero=True)
    assert_array_equal(np.isnan(data_back), [True, False])
    # Integer output with nan2zero gives zero
    aw = SlopeInterArrayWriter(arr, np.int32)
    data_back = round_trip(aw, nan2zero=True)
    assert_array_equal(data_back, [0, 99])
    # Integer output with nan2zero=False gives whatever astype gives
    data_back = round_trip(aw, nan2zero=False)
    astype_res = np.array(np.nan).astype(np.int32) * aw.slope + aw.inter
    assert_array_equal(data_back, [astype_res, 99])


def test_byte_orders():
    arr = np.arange(10, dtype=np.int32)
    # Test endian read/write of types not requiring scaling
    for tp in (np.uint64, np.float, np.complex):
        dt = np.dtype(tp)
        for code in '<>':
            ndt = dt.newbyteorder(code)
            for klass in (SlopeInterArrayWriter, SlopeArrayWriter,
                          ArrayWriter):
                aw = klass(arr, ndt)
                data_back = round_trip(aw)
                assert_array_almost_equal(arr, data_back)


def test_writers_roundtrip():
    ndt = np.dtype(np.float)
    arr = np.arange(3, dtype=ndt)
    # intercept
    aw = SlopeInterArrayWriter(arr, ndt, calc_scale=False)
    aw.inter = 1.0
    data_back = round_trip(aw)
    assert_array_equal(data_back, arr)
    # scaling
    aw.slope = 2.0
    data_back = round_trip(aw)
    assert_array_equal(data_back, arr)
    # if there is no valid data, we get zeros
    aw = SlopeInterArrayWriter(arr + np.nan, np.int32)
    data_back = round_trip(aw)
    assert_array_equal(data_back, np.zeros(arr.shape))
    # infs generate ints at same value as max
    arr[0] = np.inf
    aw = SlopeInterArrayWriter(arr, np.int32)
    data_back = round_trip(aw)
    assert_array_almost_equal(data_back, [2, 1, 2])


def test_to_float():
    for in_type in NUMERIC_TYPES:
        if in_type in IUINT_TYPES:
            info = np.iinfo(in_type)
            mn, mx, start, stop, step = info.min, info.max, 0, 100, 1
        else:
            info = np.finfo(in_type)
            mn, mx, start, stop, step = info.min, info.max, 0, 100, 0.5
        arr = np.arange(start, stop, step, dtype=in_type)
        arr[0] = mn
        arr[-1] = mx
        for out_type in CFLOAT_TYPES:
            for klass in (SlopeInterArrayWriter, SlopeArrayWriter,
                          ArrayWriter):
                if in_type in COMPLEX_TYPES and out_type in FLOAT_TYPES:
                    assert_raises(WriterError, klass, arr, out_type)
                    continue
                aw = klass(arr, out_type)
                assert_true(aw.array is arr)
                assert_equal(aw.out_dtype, out_type)
                arr_back = round_trip(aw)
                assert_array_equal(arr.astype(out_type), arr_back)
                # Check too-big values overflowed correctly
                out_min = np.finfo(out_type).min
                out_max = np.finfo(out_type).max
                assert_true(np.all(arr_back[arr > out_max] == np.inf))
                assert_true(np.all(arr_back[arr < out_min] == -np.inf))


def test_dumber_writers():
    arr = np.arange(10, dtype=np.float64)
    aw = SlopeArrayWriter(arr)
    aw.slope = 2.0
    assert_equal(aw.slope, 2.0)
    assert_raises(AttributeError, getattr, aw, 'inter')
    aw = ArrayWriter(arr)
    assert_raises(AttributeError, getattr, aw, 'slope')
    assert_raises(AttributeError, getattr, aw, 'inter')
    # Attempt at scaling should raise error for dumb type
    assert_raises(WriterError, ArrayWriter, arr, np.int16)


def test_writer_maker():
    arr = np.arange(10, dtype=np.float64)
    aw = make_array_writer(arr, np.float64)
    assert_true(isinstance(aw, SlopeInterArrayWriter))
    aw = make_array_writer(arr, np.float64, False)
    assert_true(isinstance(aw, SlopeArrayWriter))
    aw = make_array_writer(arr, np.float64, False, False)
    assert_true(isinstance(aw, ArrayWriter))
    assert_raises(ValueError, make_array_writer, arr, np.float64, True, False)
    # Does calc_scale get run by default?
    aw = make_array_writer(arr, np.int16, calc_scale=False)
    assert_equal((aw.slope, aw.inter), (1, 0))
    aw.calc_scale()
    slope, inter = aw.slope, aw.inter
    assert_false((slope, inter) == (1, 0))
    # Should run by default
    aw = make_array_writer(arr, np.int16)
    assert_equal((aw.slope, aw.inter), (slope, inter))
    aw = make_array_writer(arr, np.int16, calc_scale=True)
    assert_equal((aw.slope, aw.inter), (slope, inter))


def test_float_int():
    # Conversion between float and int
    for in_dt in FLOAT_TYPES:
        finf = np.finfo(in_dt)
        arr = np.array([finf.min, finf.max], dtype=in_dt)
        for out_dt in IUINT_TYPES:
            try:
                aw = SlopeInterArrayWriter(arr, out_dt)
            except ScalingError:
                continue
            arr_back_sc = round_trip(aw)
            assert_true(np.allclose(arr, arr_back_sc))
