def mystery(nums):
    seen = set()
    for n in nums:
        if n in seen:
            return n
        seen.add(n)
    return None
