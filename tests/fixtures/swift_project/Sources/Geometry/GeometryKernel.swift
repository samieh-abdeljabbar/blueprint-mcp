import Foundation

class GeometryKernel {
    var solver: Solver

    init() {
        self.solver = Solver()
    }

    func compute(point: Point3D) -> Point3D {
        return point
    }
}
