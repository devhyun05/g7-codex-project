import textwrap
import unittest

from tracer import ExecutionTracer


class SortingAlgorithmCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tracer = ExecutionTracer()

    def _run_sort_case(self, code: str, expected: list[int], stdin: str = ""):
        result = self.tracer.trace(textwrap.dedent(code).strip(), stdin=stdin)
        self.assertTrue(result["ok"], result["error"])
        self.assertTrue(result["analysis"]["intents"]["sorting"])
        lines = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
        self.assertTrue(lines, "stdout is empty")
        self.assertEqual(lines[-1], " ".join(map(str, expected)))

    def test_all_major_sorting_algorithms(self):
        base = [9, 4, 1, 7, 3, 8, 2, 6, 5]
        expected = sorted(base)

        cases = {
            "bubble_sort": f"""
                def bubble_sort(arr):
                    n = len(arr)
                    for i in range(n):
                        for j in range(0, n - i - 1):
                            if arr[j] > arr[j + 1]:
                                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                    return arr
                arr = {base}
                print(*bubble_sort(arr))
            """,
            "optimized_bubble_sort": f"""
                def optimized_bubble_sort(arr):
                    n = len(arr)
                    for i in range(n):
                        swapped = False
                        for j in range(0, n - i - 1):
                            if arr[j] > arr[j + 1]:
                                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                                swapped = True
                        if not swapped:
                            break
                    return arr
                arr = {base}
                print(*optimized_bubble_sort(arr))
            """,
            "selection_sort": f"""
                def selection_sort(arr):
                    n = len(arr)
                    for i in range(n):
                        min_i = i
                        for j in range(i + 1, n):
                            if arr[j] < arr[min_i]:
                                min_i = j
                        arr[i], arr[min_i] = arr[min_i], arr[i]
                    return arr
                arr = {base}
                print(*selection_sort(arr))
            """,
            "insertion_sort": f"""
                def insertion_sort(arr):
                    for i in range(1, len(arr)):
                        key = arr[i]
                        j = i - 1
                        while j >= 0 and arr[j] > key:
                            arr[j + 1] = arr[j]
                            j -= 1
                        arr[j + 1] = key
                    return arr
                arr = {base}
                print(*insertion_sort(arr))
            """,
            "binary_insertion_sort": f"""
                def binary_search(arr, key, left, right):
                    while left < right:
                        mid = (left + right) // 2
                        if arr[mid] <= key:
                            left = mid + 1
                        else:
                            right = mid
                    return left

                def binary_insertion_sort(arr):
                    for i in range(1, len(arr)):
                        key = arr[i]
                        pos = binary_search(arr, key, 0, i)
                        j = i
                        while j > pos:
                            arr[j] = arr[j - 1]
                            j -= 1
                        arr[pos] = key
                    return arr
                arr = {base}
                print(*binary_insertion_sort(arr))
            """,
            "shell_sort": f"""
                def shell_sort(arr):
                    gap = len(arr) // 2
                    while gap > 0:
                        for i in range(gap, len(arr)):
                            temp = arr[i]
                            j = i
                            while j >= gap and arr[j - gap] > temp:
                                arr[j] = arr[j - gap]
                                j -= gap
                            arr[j] = temp
                        gap //= 2
                    return arr
                arr = {base}
                print(*shell_sort(arr))
            """,
            "merge_sort_recursive": f"""
                def merge_sort(arr):
                    if len(arr) <= 1:
                        return arr
                    mid = len(arr) // 2
                    left = merge_sort(arr[:mid])
                    right = merge_sort(arr[mid:])
                    merged = []
                    i = j = 0
                    while i < len(left) and j < len(right):
                        if left[i] <= right[j]:
                            merged.append(left[i]); i += 1
                        else:
                            merged.append(right[j]); j += 1
                    merged.extend(left[i:])
                    merged.extend(right[j:])
                    return merged
                arr = {base}
                print(*merge_sort(arr))
            """,
            "merge_sort_iterative": f"""
                def merge(arr, left, mid, right):
                    i, j = left, mid
                    out = []
                    while i < mid and j < right:
                        if arr[i] <= arr[j]:
                            out.append(arr[i]); i += 1
                        else:
                            out.append(arr[j]); j += 1
                    out.extend(arr[i:mid])
                    out.extend(arr[j:right])
                    arr[left:right] = out

                def merge_sort_iterative(arr):
                    width = 1
                    n = len(arr)
                    while width < n:
                        for left in range(0, n, width * 2):
                            mid = min(left + width, n)
                            right = min(left + width * 2, n)
                            merge(arr, left, mid, right)
                        width *= 2
                    return arr
                arr = {base}
                print(*merge_sort_iterative(arr))
            """,
            "quick_sort_lomuto": f"""
                def partition(arr, low, high):
                    pivot = arr[high]
                    i = low
                    for j in range(low, high):
                        if arr[j] <= pivot:
                            arr[i], arr[j] = arr[j], arr[i]
                            i += 1
                    arr[i], arr[high] = arr[high], arr[i]
                    return i

                def quick_sort_lomuto(arr, low, high):
                    if low < high:
                        p = partition(arr, low, high)
                        quick_sort_lomuto(arr, low, p - 1)
                        quick_sort_lomuto(arr, p + 1, high)

                arr = {base}
                quick_sort_lomuto(arr, 0, len(arr) - 1)
                print(*arr)
            """,
            "quick_sort_hoare": f"""
                def partition(arr, low, high):
                    pivot = arr[(low + high) // 2]
                    i, j = low - 1, high + 1
                    while True:
                        i += 1
                        while arr[i] < pivot:
                            i += 1
                        j -= 1
                        while arr[j] > pivot:
                            j -= 1
                        if i >= j:
                            return j
                        arr[i], arr[j] = arr[j], arr[i]

                def quick_sort_hoare(arr, low, high):
                    if low < high:
                        p = partition(arr, low, high)
                        quick_sort_hoare(arr, low, p)
                        quick_sort_hoare(arr, p + 1, high)

                arr = {base}
                quick_sort_hoare(arr, 0, len(arr) - 1)
                print(*arr)
            """,
            "quick_sort_three_way": f"""
                def quick_sort_three_way(arr):
                    if len(arr) <= 1:
                        return arr
                    pivot = arr[len(arr) // 2]
                    left = [x for x in arr if x < pivot]
                    mid = [x for x in arr if x == pivot]
                    right = [x for x in arr if x > pivot]
                    return quick_sort_three_way(left) + mid + quick_sort_three_way(right)
                arr = {base}
                print(*quick_sort_three_way(arr))
            """,
            "heap_sort": f"""
                import heapq
                def heap_sort(arr):
                    heap = arr[:]
                    heapq.heapify(heap)
                    out = []
                    while heap:
                        out.append(heapq.heappop(heap))
                    return out
                arr = {base}
                print(*heap_sort(arr))
            """,
            "counting_sort": f"""
                def counting_sort(arr):
                    max_value = max(arr)
                    count = [0] * (max_value + 1)
                    for value in arr:
                        count[value] += 1
                    out = []
                    for value, freq in enumerate(count):
                        out.extend([value] * freq)
                    return out
                arr = {base}
                print(*counting_sort(arr))
            """,
            "radix_sort_lsd": f"""
                def radix_sort_lsd(arr):
                    exp = 1
                    out = arr[:]
                    max_value = max(out)
                    while max_value // exp > 0:
                        buckets = [[] for _ in range(10)]
                        for value in out:
                            buckets[(value // exp) % 10].append(value)
                        out = [value for bucket in buckets for value in bucket]
                        exp *= 10
                    return out
                arr = {base}
                print(*radix_sort_lsd(arr))
            """,
            "radix_sort_msd": f"""
                def radix_sort_msd(arr):
                    def _sort(values, exp):
                        if len(values) <= 1 or exp == 0:
                            return values
                        buckets = [[] for _ in range(10)]
                        for value in values:
                            buckets[(value // exp) % 10].append(value)
                        out = []
                        for bucket in buckets:
                            out.extend(_sort(bucket, exp // 10))
                        return out

                    max_value = max(arr)
                    exp = 1
                    while max_value // exp >= 10:
                        exp *= 10
                    return _sort(arr[:], exp)
                arr = {base}
                print(*radix_sort_msd(arr))
            """,
            "bucket_sort": f"""
                def bucket_sort(arr):
                    if not arr:
                        return arr
                    min_v, max_v = min(arr), max(arr)
                    size = max(1, (max_v - min_v) // len(arr) + 1)
                    bucket_count = (max_v - min_v) // size + 1
                    buckets = [[] for _ in range(bucket_count)]
                    for value in arr:
                        buckets[(value - min_v) // size].append(value)
                    out = []
                    for bucket in buckets:
                        bucket.sort()
                        out.extend(bucket)
                    return out
                arr = {base}
                print(*bucket_sort(arr))
            """,
            "tim_sort": f"""
                def tim_sort(arr):
                    arr = arr[:]
                    arr.sort()
                    return arr
                arr = {base}
                print(*tim_sort(arr))
            """,
            "intro_sort": f"""
                def intro_sort(arr):
                    arr = arr[:]

                    def insertion(lo, hi):
                        for i in range(lo + 1, hi):
                            key = arr[i]
                            j = i - 1
                            while j >= lo and arr[j] > key:
                                arr[j + 1] = arr[j]
                                j -= 1
                            arr[j + 1] = key

                    def recurse(lo, hi, depth):
                        if hi - lo <= 16:
                            insertion(lo, hi)
                            return
                        if depth == 0:
                            arr[lo:hi] = sorted(arr[lo:hi])
                            return
                        pivot = arr[(lo + hi) // 2]
                        i, j = lo, hi - 1
                        while i <= j:
                            while arr[i] < pivot:
                                i += 1
                            while arr[j] > pivot:
                                j -= 1
                            if i <= j:
                                arr[i], arr[j] = arr[j], arr[i]
                                i += 1
                                j -= 1
                        if lo < j + 1:
                            recurse(lo, j + 1, depth - 1)
                        if i < hi:
                            recurse(i, hi, depth - 1)

                    max_depth = (len(arr).bit_length() - 1) * 2
                    recurse(0, len(arr), max_depth)
                    return arr

                arr = {base}
                print(*intro_sort(arr))
            """,
        }

        for name, code in cases.items():
            with self.subTest(algorithm=name):
                self._run_sort_case(code, expected)

    def test_sorting_with_builtin_input(self):
        code = """
            def bubble_sort(arr):
                n = len(arr)
                for i in range(n):
                    for j in range(0, n - i - 1):
                        if arr[j] > arr[j + 1]:
                            arr[j], arr[j + 1] = arr[j + 1], arr[j]
                return arr

            n = int(input())
            arr = list(map(int, input().split()))
            print(*bubble_sort(arr[:n]))
        """
        self._run_sort_case(code, [1, 2, 4, 5, 8], stdin="5\n5 1 4 2 8\n")

    def test_sorting_with_sys_stdin_read(self):
        code = """
            import sys

            def quick_sort(arr):
                if len(arr) <= 1:
                    return arr
                pivot = arr[len(arr) // 2]
                left = [x for x in arr if x < pivot]
                mid = [x for x in arr if x == pivot]
                right = [x for x in arr if x > pivot]
                return quick_sort(left) + mid + quick_sort(right)

            data = list(map(int, sys.stdin.read().split()))
            n = data[0]
            arr = data[1:1+n]
            print(*quick_sort(arr))
        """
        self._run_sort_case(code, [1, 2, 4, 5, 8], stdin="5 5 1 4 2 8")


if __name__ == "__main__":
    unittest.main()

